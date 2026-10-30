#pragma once
#include "esp_err.h"

// Install once before starting any network workers or TLS/PSA allocations.
esp_err_t tls_memory_init(void);
