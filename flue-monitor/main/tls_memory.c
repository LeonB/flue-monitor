#include "tls_memory.h"
#include "sdkconfig.h"

#if CONFIG_MBEDTLS_CUSTOM_MEM_ALLOC
#include <stdlib.h>
#include "psram_buffer.h"
#include "mbedtls/platform.h"
#endif

esp_err_t tls_memory_init(void) {
#if CONFIG_MBEDTLS_CUSTOM_MEM_ALLOC
    // Stable for the entire boot. Do not change hooks while TLS objects exist.
    // Allocation failure propagates to TLS; never borrow scarce internal RAM.
    return mbedtls_platform_set_calloc_free(psram_buffer_calloc, free) == 0
        ? ESP_OK : ESP_FAIL;
#else
    return ESP_OK;
#endif
}
