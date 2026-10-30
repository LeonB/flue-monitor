#include "memory_diagnostics.h"
#include <stdint.h>
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "pagekite_tunnel.h"

#define CAPS (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static struct {
    uint32_t samples, largest_min, sheets_largest_min, sheets_samples, sheets_free_min;
    uint32_t sheets_attempts, sheets_completed, sheets_successes;
    bool sheets_active;
} stats;

void memory_diagnostics_sample(void) {
    uint32_t largest = heap_caps_get_largest_free_block(CAPS);
    uint32_t free_bytes = heap_caps_get_free_size(CAPS);
    portENTER_CRITICAL(&mux);
    if (!stats.samples || largest < stats.largest_min) stats.largest_min = largest;
    stats.samples++;
    if (stats.sheets_active) {
        if (!stats.sheets_samples || largest < stats.sheets_largest_min) stats.sheets_largest_min = largest;
        if (!stats.sheets_samples || free_bytes < stats.sheets_free_min) stats.sheets_free_min = free_bytes;
        stats.sheets_samples++;
    }
    portEXIT_CRITICAL(&mux);
}

void memory_diagnostics_sheets_begin(void) {
    portENTER_CRITICAL(&mux);
    stats.sheets_active = true;
    stats.sheets_attempts++;
    portEXIT_CRITICAL(&mux);
    memory_diagnostics_sample();
}

void memory_diagnostics_sheets_end(bool success) {
    memory_diagnostics_sample();
    portENTER_CRITICAL(&mux);
    stats.sheets_active = false;
    stats.sheets_completed++;
    if (success) stats.sheets_successes++;
    portEXIT_CRITICAL(&mux);
}

void memory_diagnostics_add_json(cJSON *root) {
    multi_heap_info_t info;
    heap_caps_get_info(&info, CAPS);
    portENTER_CRITICAL(&mux);
    typeof(stats) snapshot = stats;
    portEXIT_CRITICAL(&mux);
    pagekite_status_t tunnel;
    pagekite_tunnel_get_status(&tunnel);
    cJSON *memory = cJSON_AddObjectToObject(root, "memory");
    if (!memory) return;
    cJSON_AddNumberToObject(memory, "uptime_s", esp_timer_get_time() / 1000000);
    cJSON_AddNumberToObject(memory, "reset_reason", esp_reset_reason());
    cJSON_AddNumberToObject(memory, "internal_free", info.total_free_bytes);
    cJSON_AddNumberToObject(memory, "internal_min_free", info.minimum_free_bytes);
    cJSON_AddNumberToObject(memory, "internal_largest", info.largest_free_block);
#if CONFIG_FLUE_DIAG_SKIP_PSRAM_STATS
    cJSON_AddBoolToObject(memory, "psram_stats_disabled", true);
#else
    cJSON_AddNumberToObject(memory, "psram_total", heap_caps_get_total_size(MALLOC_CAP_SPIRAM));
    cJSON_AddNumberToObject(memory, "psram_free", heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    cJSON_AddNumberToObject(memory, "psram_min_free", heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM));
#endif
    cJSON_AddNumberToObject(memory, "largest_min_sampled", snapshot.largest_min);
    cJSON_AddNumberToObject(memory, "sheets_largest_min_sampled", snapshot.sheets_largest_min);
    cJSON_AddNumberToObject(memory, "sheets_free_min_sampled", snapshot.sheets_free_min);
    cJSON_AddNumberToObject(memory, "samples", snapshot.samples);
    cJSON_AddBoolToObject(memory, "sheets_active", snapshot.sheets_active);
    cJSON_AddNumberToObject(memory, "sheets_attempts", snapshot.sheets_attempts);
    cJSON_AddNumberToObject(memory, "sheets_completed", snapshot.sheets_completed);
    cJSON_AddNumberToObject(memory, "sheets_successes", snapshot.sheets_successes);
    cJSON_AddBoolToObject(memory, "pagekite_connected", tunnel.state == PAGEKITE_STATUS_CONNECTED);
}
