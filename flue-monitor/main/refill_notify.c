#include "refill_notify.h"
#include "refill_rule.h"
#include "dashboard_auth.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"

// Only small state is shared. HTTPS stays on the existing network worker.
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static refill_rule_t s_rule;
static refill_settings_t s_config;
static bool s_pending, s_test;
static int64_t s_created_ms, s_override_until;
static unsigned s_generation;
static const char *s_result = "idle";
static int s_http_status;

static bool clock_valid(time_t utc) { return utc >= 1767225600; }
static bool scheduled_quiet(const refill_settings_t *config, time_t utc) {
  if (!config->quiet_enabled) return false;
  if (!clock_valid(utc)) return true;
  return refill_quiet_minute(refill_local_minute(utc), config->quiet_start_min, config->quiet_end_min);
}

void refill_notify_sample(const sensor_reading_t *reading) {
  refill_settings_t config;
  settings_get_refill(&config);
  time_t utc = time(NULL);
  bool quiet = scheduled_quiet(&config, utc);
  int64_t now_ms = esp_timer_get_time() / 1000;
  portENTER_CRITICAL(&s_lock);
  if (memcmp(&config, &s_config, sizeof config)) {
    s_config = config;
    refill_rule_reset(&s_rule);
    s_pending = false;
    s_override_until = 0;
    ++s_generation;
  }
  if (!config.enabled) refill_rule_reset(&s_rule);
  else if (refill_rule_sample(&s_rule, now_ms,
             reading->thermocouple_ok && thermocouple_reading_plausible(reading->thermocouple_c),
             reading->thermocouple_c, reading->thermocouple_rate_c_per_min, config.threshold_c)) {
    // Quiet candidates are consumed, not held until morning.
    if (!clock_valid(utc) || (quiet && utc >= s_override_until)) s_result = "quiet";
    else if (!s_pending) {
      s_pending = true; s_test = false; s_created_ms = now_ms;
      ++s_generation; s_result = "pending";
    }
  }
  portEXIT_CRITICAL(&s_lock);
  memset(&config, 0, sizeof config);
}

void refill_notify_manual_event(const char *event) {
  if (strcmp(event, "added_wood") && strcmp(event, "cold_start") && strcmp(event, "stove_off")) return;
  portENTER_CRITICAL(&s_lock);
  refill_rule_reset(&s_rule);
  s_pending = false;
  ++s_generation;
  portEXIT_CRITICAL(&s_lock);
}

void refill_notify_send_pending(const settings_t *settings) {
  time_t utc = time(NULL);
  bool quiet = scheduled_quiet(&settings->refill, utc);
  int64_t now_ms = esp_timer_get_time() / 1000;
  sensor_reading_t reading;
  sensors_get_last_reading(&reading);
  bool test;
  unsigned generation;
  portENTER_CRITICAL(&s_lock);
  if (!s_pending) { portEXIT_CRITICAL(&s_lock); return; }
  test = s_test;
  generation = s_generation;
  // Never deliver old/quiet/invalid-sensor candidates after a worker backlog.
  bool discard = memcmp(&settings->refill, &s_config, sizeof s_config) || !*settings->refill.url || !clock_valid(utc) || now_ms - s_created_ms > 120000 ||
    (!test && (!settings->refill.enabled || (quiet && utc >= s_override_until) ||
      !reading.thermocouple_ok || !thermocouple_reading_plausible(reading.thermocouple_c) ||
      reading.thermocouple_c > settings->refill.threshold_c || reading.thermocouple_rate_c_per_min > 0));
  s_pending = false;
  s_result = discard ? "skipped" : "sending";
  portEXIT_CRITICAL(&s_lock);
  if (discard) return;

  const char *body = test ? "Testmelding van je Flue Monitor." :
    "De kachel koelt af. Wil je doorstoken? Kijk of bijvullen nodig is.";
  esp_http_client_config_t config = {
    .url = settings->refill.url, .method = HTTP_METHOD_POST,
    .timeout_ms = 10000, .buffer_size_tx = 1024, .disable_auto_redirect = true,
    .crt_bundle_attach = esp_crt_bundle_attach,
  };
  esp_http_client_handle_t client = esp_http_client_init(&config);
  int status = 0;
  bool sent = false;
  if (client) {
    bool ready = esp_http_client_set_header(client, "Content-Type", "text/plain; charset=utf-8") == ESP_OK &&
      esp_http_client_set_header(client, "Title", test ? "Flue Monitor - test" : "Flue Monitor - bijvullen?") == ESP_OK &&
      esp_http_client_set_header(client, "Priority", "default") == ESP_OK;
    char authorization[144];
    if (*settings->refill.token) {
      snprintf(authorization, sizeof authorization, "Bearer %s", settings->refill.token);
      ready = esp_http_client_set_header(client, "Authorization", authorization) == ESP_OK && ready;
    }
    char click[160];
    if (settings->cloudflare.enabled && *settings->cloudflare.hostname) {
      snprintf(click, sizeof click, "https://%s/", settings->cloudflare.hostname);
      ready = esp_http_client_set_header(client, "Click", click) == ESP_OK && ready;
    }
    ready = esp_http_client_set_post_field(client, body, strlen(body)) == ESP_OK && ready;
    esp_err_t err = ready ? esp_http_client_perform(client) : ESP_FAIL;
    status = esp_http_client_get_status_code(client);
    sent = err == ESP_OK && status >= 200 && status < 300;
    esp_http_client_cleanup(client);
    memset(authorization, 0, sizeof authorization);
  }
  portENTER_CRITICAL(&s_lock);
  if (generation == s_generation) {
    s_result = sent ? "sent" : "failed";
    s_http_status = status;
  }
  portEXIT_CRITICAL(&s_lock);
  // A timeout may already have delivered the message. Do not retry and duplicate
  // it, or send a stale reminder after the fire has changed.
}

static esp_err_t status_handler(web_request_t *req) {
  if (!dashboard_auth_check(req)) {
    web_set_status(req, "401 Unauthorized"); return web_sendstr(req, "{}");
  }
  refill_settings_t config;
  settings_get_refill(&config);
  time_t utc = time(NULL);
  bool quiet = scheduled_quiet(&config, utc);
  char json[192];
  portENTER_CRITICAL(&s_lock);
  int64_t override_until = s_override_until;
  bool armed = s_rule.armed;
  const char *result = s_result;
  int http_status = s_http_status;
  portEXIT_CRITICAL(&s_lock);
  snprintf(json, sizeof json, "{\"quiet\":%s,\"override_until\":%lld,\"armed\":%s,\"result\":\"%s\",\"http_status\":%d}",
    quiet && utc >= override_until ? "true" : "false", (long long)override_until,
    armed ? "true" : "false", result, http_status);
  memset(&config, 0, sizeof config);
  web_set_type(req, "application/json"); web_set_header(req, "Cache-Control", "no-store");
  return web_sendstr(req, json);
}

static esp_err_t action_handler(web_request_t *req) {
  if (!dashboard_auth_check(req)) { web_set_status(req, "401 Unauthorized"); return web_sendstr(req, "{}"); }
  if (!dashboard_auth_check_csrf(req)) return web_send_err(req, HTTPD_403_FORBIDDEN, "Invalid request origin");
  char body[3] = {0};
  if (req->content_len != 2) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Expected an empty JSON object");
  size_t got = 0;
  while (got < 2) {
    int n = web_recv(req, body + got, 2 - got);
    if (n <= 0) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Incomplete request");
    got += n;
  }
  if (strcmp(body, "{}")) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Expected an empty JSON object");
  refill_settings_t config;
  settings_get_refill(&config);
  time_t utc = time(NULL);
  if (!clock_valid(utc)) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Monitor clock not ready");
  bool test = !strcmp(req->uri, "/api/refill/test");
  if (test && !*config.url) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Save an ntfy destination first");
  int64_t until = 0;
  if (!strcmp(req->uri, "/api/refill/allow-tonight")) {
    until = refill_next_quiet_end(utc, config.quiet_end_min);
  }
  portENTER_CRITICAL(&s_lock);
  if (memcmp(&config, &s_config, sizeof config)) {
    s_config = config; refill_rule_reset(&s_rule); s_pending = false; s_override_until = 0;
    ++s_generation;
  }
  if (test) {
    s_pending = true; s_test = true; s_created_ms = esp_timer_get_time() / 1000;
    s_result = "pending"; ++s_generation;
  } else s_override_until = until;
  portEXIT_CRITICAL(&s_lock);
  memset(&config, 0, sizeof config);
  web_set_type(req, "application/json"); web_set_header(req, "Cache-Control", "no-store");
  return web_sendstr(req, "{\"success\":true}");
}

void refill_notify_register(httpd_handle_t server) {
  static const web_route_t routes[] = {
    { .uri = "/api/refill/status", .method = HTTP_GET, .handler = status_handler },
    { .uri = "/api/refill/test", .method = HTTP_POST, .handler = action_handler },
    { .uri = "/api/refill/allow-tonight", .method = HTTP_POST, .handler = action_handler },
    { .uri = "/api/refill/quiet", .method = HTTP_POST, .handler = action_handler },
  };
  for (size_t i = 0; i < sizeof routes / sizeof routes[0]; ++i)
    ESP_ERROR_CHECK(web_register_handler(server, &routes[i]));
}
