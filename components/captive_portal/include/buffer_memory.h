#pragma once
#include "sdkconfig.h"
#include "esp_heap_caps.h"
#include "esp_log.h"

// Only for ordinary task-context data, never DMA buffers or task stacks.
// PSRAM-enabled firmware must never borrow internal RAM for these buffers.
// The display is built without PSRAM and deliberately uses internal RAM.
#if CONFIG_SPIRAM
#define BUFFER_MEMORY_CAPS (MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
#else
#define BUFFER_MEMORY_CAPS (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)
#endif
static inline void *buffer_memory_alloc(size_t size) {
  void *buffer = heap_caps_malloc(size, BUFFER_MEMORY_CAPS);
  if (!buffer) ESP_LOGE("buffer_memory", "Buffer allocation failed (%zu bytes, caps=0x%x)", size, BUFFER_MEMORY_CAPS);
  return buffer;
}

static inline void *buffer_memory_calloc(size_t count, size_t size) {
  void *buffer = heap_caps_calloc(count, size, BUFFER_MEMORY_CAPS);
  if (!buffer) ESP_LOGE("buffer_memory", "Buffer allocation failed (%zu x %zu bytes, caps=0x%x)", count, size, BUFFER_MEMORY_CAPS);
  return buffer;
}
