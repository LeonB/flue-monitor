#pragma once
#include <stdint.h>
#include "cJSON.h"

typedef enum {
    STACK_MAIN, STACK_SENSOR, STACK_SHEETS, STACK_BOSCH, STACK_PAGEKITE, STACK_HTTP,
    STACK_TASK_COUNT
} stack_task_t;

enum {
    SENSOR_STACK_BYTES = 4096, SHEETS_STACK_BYTES = 12288,
    BOSCH_STACK_BYTES = 8192, PAGEKITE_STACK_BYTES = 12288, HTTP_STACK_BYTES = 8192
};

// Call from the task itself. Registered tasks must remain alive until reboot.
void stack_diagnostics_register(stack_task_t slot, uint32_t size_bytes);
// Call periodically from main, outside critical sections. No new worker task.
void stack_diagnostics_sample(void);
void stack_diagnostics_add_json(cJSON *memory);
