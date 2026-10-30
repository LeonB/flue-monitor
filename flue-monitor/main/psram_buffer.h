#pragma once
#include "esp_heap_caps.h"
#include "esp_log.h"

// Network payloads must not consume internal RAM when PSRAM is unavailable.
// Use only in task context, never for DMA, interrupt data or task stacks.
static inline void *psram_buffer_alloc(size_t size) {
    void *buffer = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buffer) ESP_LOGE("psram_buffer", "PSRAM allocation failed (%zu bytes)", size);
    return buffer;
}

static inline void *psram_buffer_calloc(size_t count, size_t size) {
    void *buffer = heap_caps_calloc(count, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buffer) ESP_LOGE("psram_buffer", "PSRAM allocation failed (%zu x %zu bytes)", count, size);
    return buffer;
}
