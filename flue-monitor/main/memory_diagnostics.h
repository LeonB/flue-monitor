#pragma once
#include <stdbool.h>
#include "cJSON.h"

// Sample internal, byte-addressable RAM; largest-block minima are sampled,
// whereas the allocator's minimum-free counter also catches shorter peaks.
void memory_diagnostics_sample(void);
void memory_diagnostics_sheets_begin(void);
void memory_diagnostics_sheets_end(bool success);
void memory_diagnostics_add_json(cJSON *root);
