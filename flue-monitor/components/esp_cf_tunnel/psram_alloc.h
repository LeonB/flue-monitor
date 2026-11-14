#pragma once
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "sdkconfig.h"
#include "esp_heap_caps.h"

// Force only the tunnel and HTTP/2 data allocations into external RAM.
// Task stacks, synchronization primitives, Wi-Fi and DMA stay internal.
// No internal fallback on PSRAM-enabled targets.
#if CONFIG_SPIRAM
static inline void *cft_data_malloc(size_t n) {
  return heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
static inline void *cft_data_calloc(size_t n, size_t size) {
  if (size && n > SIZE_MAX / size) return NULL;
  return heap_caps_calloc(n, size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
static inline void *cft_data_realloc(void *p, size_t n) {
  return heap_caps_realloc(p, n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
}
static inline char *cft_data_strdup(const char *s) {
  size_t n = strlen(s) + 1;
  char *p = cft_data_malloc(n);
  if (p) memcpy(p, s, n);
  return p;
}
#define strdup cft_data_strdup
#define malloc cft_data_malloc
#define calloc cft_data_calloc
#define realloc cft_data_realloc
#endif
