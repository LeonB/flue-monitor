#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "cf_tunnel_esp.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "nvs_flash.h"

static EventGroupHandle_t network;
static char token[4096];

/* Test credentials exist only in RAM; never echo serial input. */
static void read_line(const char *prompt, char *out, size_t capacity)
{
    puts(prompt);
    fflush(stdout);
    int64_t prompted_at = esp_timer_get_time();
    size_t used = 0;
    bool overflow = false;
    while (true) {
        unsigned char ch;
        if (read(STDIN_FILENO, &ch, 1) != 1) {
            if (used == 0 && esp_timer_get_time() - prompted_at >= 5000000) {
                puts(prompt);
                fflush(stdout);
                prompted_at = esp_timer_get_time();
            }
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        if (ch == '\r') {
            continue;
        }
        if (ch == '\n') {
            if (overflow) {
                puts("INPUT_TOO_LONG");
                abort();
            }
            out[used] = 0;
            return;
        }
        if (used + 1 < capacity) {
            out[used++] = (char)ch;
        } else {
            overflow = true;
        }
    }
}

static void network_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && (id == WIFI_EVENT_STA_START || id == WIFI_EVENT_STA_DISCONNECTED)) {
        xEventGroupClearBits(network, BIT0);
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(network, BIT0);
    }
}

static void ws_echo(cft_stream_t *stream, void *ctx, cft_ws_opcode_t opcode,
                    const uint8_t *data, size_t len)
{
    if (opcode == CFT_WS_TEXT || opcode == CFT_WS_BINARY) {
        cft_ws_send(stream, opcode, data, len);
    }
}

static void body_echo(cft_stream_t *stream, void *ctx, const uint8_t *body, size_t len)
{
    cft_stream_respond(stream, 200, "application/octet-stream", body, len);
}

static void on_request(void *arg, cft_stream_t *stream, const cft_request_t *request)
{
    if (strcmp(request->path, "/ws") == 0 && request->is_websocket) {
        cft_stream_handlers_t handlers = {.on_ws_message = ws_echo};
        cft_stream_set_handlers(stream, &handlers, NULL);
        cft_ws_accept(stream, NULL);
    } else if (strcmp(request->path, "/echo") == 0 && strcmp(request->method, "POST") == 0) {
        cft_stream_read_body(stream, 4096, body_echo, NULL);
    } else if (strcmp(request->path, "/status") == 0 && strcmp(request->method, "GET") == 0) {
        char body[256];
        int n = snprintf(body, sizeof(body),
                         "{\"probe\":\"cloudflare-s3\",\"uptime_us\":%lld,"
                         "\"internal_free\":%u,\"internal_largest\":%u,\"internal_minimum\":%u}\n",
                         (long long)esp_timer_get_time(),
                         (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                         (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                         (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
        cft_stream_respond(stream, 200, "application/json", body, (size_t)n);
    } else {
        cft_stream_respond(stream, 404, "text/plain", "not found\n", 10);
    }
}

void app_main(void)
{
    /* Never erase an existing NVS partition automatically. */
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    network = xEventGroupCreate();
    assert(network != NULL);
    assert(esp_netif_create_default_wifi_sta() != NULL);
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, network_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, network_event, NULL));

    char ssid[33], password[65];
    read_line("PROBE_SSID", ssid, sizeof(ssid));
    read_line("PROBE_PASSWORD", password, sizeof(password));
    read_line("PROBE_TUNNEL_TOKEN", token, sizeof(token));
    wifi_config_t wifi = {0};
    memcpy(wifi.sta.ssid, ssid, strlen(ssid));
    memcpy(wifi.sta.password, password, strlen(password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi));
    memset(password, 0, sizeof(password));
    memset(wifi.sta.password, 0, sizeof(wifi.sta.password));
    ESP_ERROR_CHECK(esp_wifi_start());
    xEventGroupWaitBits(network, BIT0, pdFALSE, pdTRUE, portMAX_DELAY);
    puts("PROBE_WIFI_READY");

    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
    for (int i = 0; i < 120 && time(NULL) < 1767225600; ++i) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    if (time(NULL) < 1767225600) {
        puts("PROBE_TIME_FAILED");
        return;
    }
    cft_tunnel_config_t config = {
        .token = token,
        .on_request = on_request,
        .num_connections = 1,
        .max_concurrent_streams = 4,
        .max_request_body = 4096,
        .stream_window = 4096,
    };
    cft_tunnel_handle_t tunnel;
    ESP_ERROR_CHECK(cft_tunnel_start(&config, &tunnel));
    memset(token, 0, sizeof(token));
    puts("PROBE_TUNNEL_STARTED");
    for (;;) {
        printf("PROBE_HEAP internal=%u largest=%u minimum=%u\n",
               (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
               (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
               (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
