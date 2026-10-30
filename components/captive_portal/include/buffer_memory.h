#pragma once
#include "esp_heap_caps.h"

// Only for ordinary task-context data, never DMA buffers or task stacks.
// Keep working when PSRAM is absent or full (including the display firmware).
static inline void *buffer_memory_alloc(size_t size) {
  return heap_caps_malloc_prefer(size, 2,
      MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT,
      MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
}

static inline void *buffer_memory_calloc(size_t count, size_t size) {
  return heap_caps_calloc_prefer(count, size, 2,
      MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT,
      MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
}
