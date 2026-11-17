#include "settings.h"
#include "flight_recorder.h"

#include <string.h>
#include <stddef.h>
#include <math.h>
#include <stdlib.h>
#include "buffer_memory.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"

#include "config.h"

static const char *TAG = "settings";

#define NVS_NAMESPACE "settings"
#define NVS_KEY_LEGACY "settings_v1"
#define NVS_KEY_BLOB  "settings_v5"  // whole settings_t as one blob -- see settings_set()'s own doc comment for why

static settings_t *s_settings;
static SemaphoreHandle_t s_mutex;

static void set_defaults(settings_t *s) {
  memset(s, 0, sizeof(*s));
  s->log_heartbeat_min = DEFAULT_LOG_HEARTBEAT_MIN;
  s->zone_cold_max_c = DEFAULT_ZONE_COLD_MAX_C;
  s->zone_optimal_max_c = DEFAULT_ZONE_OPTIMAL_MAX_C;
  s->fast_rise_c_per_min = DEFAULT_FAST_RISE_C_PER_MIN;
  s->thermocouple_deadband_c = DEFAULT_THERMOCOUPLE_DEADBAND_C;
  // google_sheets_webhook_url/secret left empty -- no safe compile-time
  // default; Milestone 5's Sheets logging has nothing to do until these are
  // set via POST /api/settings.
  s->idle_pulse_period_ms = DEFAULT_IDLE_PULSE_PERIOD_MS;
  s->fast_pulse_period_ms = DEFAULT_FAST_PULSE_PERIOD_MS;
  s->rate_deadband_c_per_min = DEFAULT_RATE_DEADBAND_C_PER_MIN;
  s->color_transition_exponent = DEFAULT_COLOR_TRANSITION_EXPONENT;
  strcpy(s->zone_cold_color, "#003cff");
  strcpy(s->zone_optimal_color, "#ff3700");
  strcpy(s->zone_hot_color, "#ff0000");
  s->breathing_exponent = DEFAULT_BREATHING_EXPONENT;
  s->minimum_brightness = DEFAULT_MINIMUM_BRIGHTNESS;
  s->maximum_brightness = DEFAULT_MAXIMUM_BRIGHTNESS;
  s->cloudflare.connections = 1;
  s->burn_end_temperature_c = 60.0f;
  s->refill.threshold_c = 80.0f;
  s->refill.quiet_enabled = 1;
  s->refill.quiet_start_min = 23 * 60;
  s->refill.quiet_end_min = 7 * 60;
}

static bool valid_color(const char color[8]) {
  if (color[0] != '#' || color[7] != '\0') return false;
  for (int i = 1; i <= 6; i++) {
    char c = color[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
  }
  return true;
}

// Bare DNS names or IPv4 addresses only: prevent protocol/header injection.
static bool valid_host(const char *host) {
  size_t n = strnlen(host, SETTINGS_CLOUDFLARE_HOST_MAX_LEN);
  if (!n || n >= SETTINGS_CLOUDFLARE_HOST_MAX_LEN) return false;
  size_t label = 0;
  for (size_t i = 0; i < n; i++) {
    char c = host[i];
    if (c == '.') {
      if (!label || host[i - 1] == '-') return false;
      label = 0;
    } else {
      if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return false;
      if ((!label && c == '-') || ++label > 63) return false;
    }
  }
  return label && host[n - 1] != '-';
}
static bool valid_cloudflare(const cloudflare_settings_t *c) {
  if (c->enabled > 1 || c->connections < 1 || c->connections > 4) return false;
  if (*c->hostname && !valid_host(c->hostname)) return false;
  size_t n = strnlen(c->token, sizeof c->token);
  if (n >= sizeof c->token) return false;
  for (size_t i = 0; i < n; i++) {
    unsigned char ch = c->token[i];
    if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
          (ch >= '0' && ch <= '9') || ch == '+' || ch == '/' || ch == '=' || ch == '-' || ch == '_')) return false;
  }
  return !c->enabled || (*c->hostname && n >= 16);
}

static bool valid_refill(const refill_settings_t *r) {
  if (r->enabled > 1 || r->quiet_enabled > 1 || !isfinite(r->threshold_c) ||
      r->threshold_c < 40 || r->threshold_c > 150 || r->quiet_start_min >= 1440 ||
      r->quiet_end_min >= 1440 || (r->quiet_enabled && r->quiet_start_min == r->quiet_end_min)) return false;
  size_t n = strnlen(r->url, sizeof r->url);
  if (n >= sizeof r->url || strnlen(r->token, sizeof r->token) >= sizeof r->token) return false;
  if (n) {
    if (strncmp(r->url, "https://", 8)) return false;
    const char *topic = strchr(r->url + 8, '/');
    if (!topic || topic == r->url + 8 || !topic[1]) return false;
    for (const char *p = r->url + 8; p < topic; ++p)
      if (!( (*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
             (*p >= '0' && *p <= '9') || *p == '.' || *p == '-' || *p == ':')) return false;
    for (const char *p = topic + 1; *p; ++p)
      if (!( (*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
             (*p >= '0' && *p <= '9') || *p == '_' || *p == '-')) return false;
  }
  for (const char *p = r->token; *p; ++p) if ((unsigned char)*p < 33 || (unsigned char)*p > 126) return false;
  return !r->enabled || n > 0;
}

static bool validate(const settings_t *s) {
  const float numbers[] = {s->zone_cold_max_c, s->zone_optimal_max_c,
    s->fast_rise_c_per_min, s->thermocouple_deadband_c, s->rate_deadband_c_per_min,
    s->color_transition_exponent, s->breathing_exponent, s->burn_end_temperature_c};
  for (size_t i = 0; i < sizeof numbers / sizeof numbers[0]; i++)
    if (!isfinite(numbers[i])) return false;
  if (!valid_cloudflare(&s->cloudflare) || !valid_refill(&s->refill)) return false;
  if (s->burn_end_temperature_c < 0.0f || s->burn_end_temperature_c >= s->zone_cold_max_c) return false;
  if (s->maximum_brightness > 255 || s->minimum_brightness > s->maximum_brightness) return false;
  if (s->breathing_exponent < 0.3f || s->breathing_exponent > 3.0f) return false;
  if (!valid_color(s->zone_cold_color) || !valid_color(s->zone_optimal_color) || !valid_color(s->zone_hot_color)) return false;
  if (s->zone_cold_max_c >= s->zone_optimal_max_c) {
    return false;
  }
  if (s->fast_rise_c_per_min <= 0.0f) {
    return false;
  }
  if (s->log_heartbeat_min == 0) {
    return false;
  }
  if (s->thermocouple_deadband_c < 0.0f) {
    return false;
  }
  if (s->idle_pulse_period_ms == 0 || s->fast_pulse_period_ms == 0) {
    return false;
  }
  if (s->rate_deadband_c_per_min < 0.0f) {
    return false;
  }
  if (s->color_transition_exponent <= 0.0f) {
    return false;
  }
  return true;
}

void settings_init(void) {
  s_mutex = xSemaphoreCreateMutex();

  // Large settings/token snapshots belong in PSRAM, not on the main stack.
  settings_t *loaded = buffer_memory_calloc(1, sizeof *loaded);
  if (!loaded) abort();
  set_defaults(loaded);
  nvs_handle_t handle;
  if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle) == ESP_OK) {
    // New writes omit the retired tunnel block. Keep previous keys untouched
    // so rollback images retain their own layout and credentials.
    const size_t prefix = offsetof(settings_t, cloudflare);
    const size_t old_cloudflare = prefix + 516;
    const char *keys[] = {NVS_KEY_BLOB, "settings_v4", "settings_v3", "settings_v2", NVS_KEY_LEGACY};
    for (size_t i = 0; i < sizeof keys / sizeof keys[0]; i++) {
      size_t len = 0;
      if (nvs_get_blob(handle, keys[i], NULL, &len) != ESP_OK) continue;
      bool current = i < 3;
      bool full_old = len == old_cloudflare + sizeof(cloudflare_settings_t);
      bool supported = current ? len == (i == 0 ? sizeof(settings_t) : i == 1 ? offsetof(settings_t, refill) : offsetof(settings_t, burn_end_temperature_c)) :
          full_old || len == old_cloudflare || len == old_cloudflare + 16 ||
          len == old_cloudflare + 20 || len == prefix + 388 || len == prefix ||
          len == offsetof(settings_t, zone_cold_color) ||
          len == offsetof(settings_t, breathing_exponent) ||
          len == offsetof(settings_t, maximum_brightness);
      if (supported) {
        void *stored = buffer_memory_calloc(1, len);
        if (!stored) abort();
        size_t read_len = len;
        if (nvs_get_blob(handle, keys[i], stored, &read_len) == ESP_OK && read_len == len) {
          if (current) memcpy(loaded, stored, len);
          else {
            memcpy(loaded, stored, len < prefix ? len : prefix);
            if (full_old) memcpy(&loaded->cloudflare, (char *)stored + old_cloudflare,
                                 sizeof loaded->cloudflare);
          }
          // Seed the new field below even an unusually low legacy cold limit.
          if (i > 1) loaded->burn_end_temperature_c = fminf(60.0f, fmaxf(0.0f, loaded->zone_cold_max_c - 1.0f));
          if (!validate(loaded)) set_defaults(loaded);
        }
        memset(stored, 0, len);
        free(stored);
      }
      break; // An invalid current blob must not resurrect stale settings.
    }
    nvs_close(handle);
  }
  if (s_settings) { memset(s_settings, 0, sizeof *s_settings); free(s_settings); }
  s_settings = loaded;
}

void settings_get(settings_t *out) {
  xSemaphoreTake(s_mutex, portMAX_DELAY);
  *out = *s_settings;
  xSemaphoreGive(s_mutex);
}

void settings_get_cloudflare(cloudflare_settings_t *out) {
  xSemaphoreTake(s_mutex, portMAX_DELAY);
  *out = s_settings->cloudflare;
  xSemaphoreGive(s_mutex);
}

void settings_get_refill(refill_settings_t *out) {
  xSemaphoreTake(s_mutex, portMAX_DELAY);
  *out = s_settings->refill;
  xSemaphoreGive(s_mutex);
}

float settings_get_burn_end_temperature(void) {
  xSemaphoreTake(s_mutex, portMAX_DELAY);
  float temperature = s_settings->burn_end_temperature_c;
  xSemaphoreGive(s_mutex);
  return temperature;
}

void settings_get_zone_limits(float *cold_max_c, float *optimal_max_c) {
  xSemaphoreTake(s_mutex, portMAX_DELAY);
  *cold_max_c = s_settings->zone_cold_max_c;
  *optimal_max_c = s_settings->zone_optimal_max_c;
  xSemaphoreGive(s_mutex);
}

esp_err_t settings_set(const settings_t *new_settings) {
  if (!validate(new_settings)) {
    return ESP_ERR_INVALID_ARG;
  }

  nvs_handle_t handle;
  esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
  if (err != ESP_OK) {
    return err;
  }
  FLUE_TRACE(NVS_BEGIN,sizeof *new_settings);
  err = nvs_set_blob(handle, NVS_KEY_BLOB, new_settings, sizeof(*new_settings));
  if (err == ESP_OK) {
    err = nvs_commit(handle);
  }
  nvs_close(handle);
  FLUE_TRACE(NVS_END,err);
  if (err != ESP_OK) {
    return err;
  }

  xSemaphoreTake(s_mutex, portMAX_DELAY);
  *s_settings = *new_settings;
  xSemaphoreGive(s_mutex);
  return ESP_OK;
}
