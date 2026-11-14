#include "cloudflare_tunnel.h"
#include "rest_api.h"
#include "cloudflare_policy.h"
#include "cloudflare_queue.h"
#include "settings.h"
#include "buffer_memory.h"
#include "stack_diagnostics.h"
#include "cf_tunnel_esp.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <stdlib.h>
#include <time.h>

static const char *TAG = "cloudflare";
static TaskHandle_t worker;
static SemaphoreHandle_t control;
static cft_tunnel_t *active;
static uint32_t generation;
static int64_t restart_after_us;
static bool draining;
static portMUX_TYPE status_mux = portMUX_INITIALIZER_UNLOCKED;
static cloudflare_status_t status;
static uint8_t registered;

void cloudflare_tunnel_get_status(cloudflare_status_t *out) {
  portENTER_CRITICAL(&status_mux);
  *out = status;
  portEXIT_CRITICAL(&status_mux);
}
static void set_state(cloudflare_status_state_t state, uint32_t configured) {
  portENTER_CRITICAL(&status_mux);
  status.state = state;
  status.configured_connections = configured;
  status.connections = 0;
  registered = 0;
  portEXIT_CRITICAL(&status_mux);
}
static void on_event(void *arg, const cft_event_t *event) {
  (void)arg;
  if (event->conn_index >= 4) return;
  portENTER_CRITICAL(&status_mux);
  if (event->type == CFT_EVENT_REGISTERED) registered |= 1U << event->conn_index;
  if (event->type == CFT_EVENT_CLOSED || event->type == CFT_EVENT_UNREGISTERED)
    registered &= ~(1U << event->conn_index);
  status.connections = __builtin_popcount(registered);
  if (registered) status.state = CLOUDFLARE_STATUS_CONNECTED;
  else if (event->type == CFT_EVENT_REGISTRATION_FAILED) status.state = CLOUDFLARE_STATUS_AUTH_ERROR;
  else if (event->type == CFT_EVENT_CLOSED) status.state = CLOUDFLARE_STATUS_NETWORK_ERROR;
  portEXIT_CRITICAL(&status_mux);
}
static void on_request(void *arg, cft_stream_t *stream, const cft_request_t *req) {
  const cloudflare_settings_t *config = arg;
  // Host and HTTPS come from the edge; loopback peer classification in HTTPD
  // still enforces remote authentication/CSRF and forbids LAN-only enrollment.
  if (!req->authority || strcasecmp(req->authority, config->hostname) ||
      !req->scheme || strcmp(req->scheme, "https")) {
    cft_stream_respond(stream, 403, "text/plain", "HTTPS hostname required\n", 24);
    return;
  }
  if (!cloudflare_route_allowed(req->method, req->path, req->is_websocket)) {
    cft_stream_respond(stream, 404, "text/plain", "Not found\n", 10);
    return;
  }
  if (!strcmp(req->method, "POST")) {
    const char *type = cft_stream_header(stream, "content-type");
    if (req->content_length < 0 || req->content_length >= 8192 ||
        !type || (strcmp(type, "application/json") && strncmp(type, "application/json;", 17))) {
      cft_stream_respond(stream, 400, "text/plain", "Invalid JSON request\n", 21);
      return;
    }
  }
  // Never use remote ingress service URLs as origin addresses. Cookie, Origin,
  // Host and asset queries pass through the bounded HTTP proxy unchanged.
  if (!strcmp(req->method, "GET")) {
    if (req->content_length > 0) {
      cft_stream_respond(stream, 400, "text/plain", "GET body not supported\n", 23);
      return;
    }
    if (!rest_api_tunnel_font(stream, req->path)) queue_get(stream, esp_timer_get_time());
  } else if (cft_stream_proxy(stream, "http://127.0.0.1:80") < 0) {
    cft_stream_respond(stream, 502, "text/plain", "Proxy unavailable\n", 18);
  }
}
static void on_poll(void *arg) {
  (void)arg;
  xSemaphoreTake(control, portMAX_DELAY);
  // Keep processing HTTP for a grace interval before unregistering. The
  // unregister ACK can close the connection immediately, even with a stop timeout.
  if (active && restart_after_us && esp_timer_get_time() >= restart_after_us) {
    cft_tunnel_request_stop(active, 3000);
    restart_after_us = 0;
    draining = true;
  }
  xSemaphoreGive(control);
  if (!draining) pump_gets(esp_timer_get_time());
}
static void task(void *arg) {
  (void)arg;
  stack_diagnostics_register(STACK_CLOUDFLARE, CLOUDFLARE_STACK_BYTES);
  cloudflare_settings_t *config = buffer_memory_calloc(1, sizeof *config);
  if (!config) {
    set_state(CLOUDFLARE_STATUS_NETWORK_ERROR, 0);
    for (;;) vTaskSuspend(NULL);
  }
  uint8_t connector[16] = {0x66, 0x6c, 0x75, 0x65, 0x2d, 0x63, 0x80, 0, 0x80, 0};
  esp_read_mac(connector + 10, ESP_MAC_BASE);
  for (;;) {
    xSemaphoreTake(control, portMAX_DELAY);
    uint32_t version = generation;
    xSemaphoreGive(control);
    settings_get_cloudflare(config);
    set_state(config->enabled ? CLOUDFLARE_STATUS_CONNECTING : CLOUDFLARE_STATUS_DISABLED,
              config->connections);
    if (!config->enabled) { ulTaskNotifyTake(pdTRUE, portMAX_DELAY); continue; }
    // SNTP is started by main. Never disable certificate verification for boot.
    if (time(NULL) < 1767225600) { ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000)); continue; }
    cft_tunnel_config_t cfg = {
      .token = config->token, .num_connections = config->connections,
      .on_request = on_request, .request_arg = config, .on_event = on_event,
      .on_poll = on_poll,
      .connector_id = connector, .arch = CONFIG_IDF_TARGET,
      .max_concurrent_streams = 16, .max_request_body = 8192,
      .max_origin_connections = 4, .stream_window = 4096, .proxy_buffer_size = 4096,
    };
    cft_tunnel_t *tunnel = cft_tunnel_new(&cfg, &cft_transport_esp);
    if (!tunnel) {
      set_state(CLOUDFLARE_STATUS_AUTH_ERROR, config->connections);
      ESP_LOGW(TAG, "Tunnel configuration rejected or insufficient memory");
      ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(30000));
      continue;
    }
    xSemaphoreTake(control, portMAX_DELAY);
    if (version != generation) {
      xSemaphoreGive(control);
      cft_tunnel_free(tunnel);
      continue;
    }
    restart_after_us = 0;
    active = tunnel;
    draining = false;
    xSemaphoreGive(control);
    cft_tunnel_run(tunnel);
    xSemaphoreTake(control, portMAX_DELAY);
    active = NULL;
    xSemaphoreGive(control);
    cft_tunnel_free(tunnel);
    reset_gets();
    memset(config, 0, sizeof *config);
    // The library handles network reconnects. A completed run means a saved
    // configuration change; resnapshot immediately, including disable/re-enable.
    ulTaskNotifyTake(pdTRUE, 0);
  }
}
void cloudflare_tunnel_start(void) {
  if (!control) control = xSemaphoreCreateMutex();
  if (!control) { set_state(CLOUDFLARE_STATUS_NETWORK_ERROR, 0); return; }
  xSemaphoreTake(control, portMAX_DELAY);
  generation++;
  // Let the tunnel forward the save response before unregistering.
  if (active) restart_after_us = esp_timer_get_time() + 1000000;
  if (!worker) {
    if (xTaskCreate(task, "cloudflare", CLOUDFLARE_STACK_BYTES, NULL, 1, &worker) != pdPASS)
      set_state(CLOUDFLARE_STATUS_NETWORK_ERROR, 0);
  } else xTaskNotifyGive(worker);
  xSemaphoreGive(control);
}
