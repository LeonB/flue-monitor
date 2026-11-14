#include "stack_diagnostics.h"
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static struct stack_entry {
    TaskHandle_t task;
    uint32_t size_bytes, min_free_bytes;
    bool measured;
} entries[STACK_TASK_COUNT];

void stack_diagnostics_register(stack_task_t slot, uint32_t size_bytes) {
    if ((unsigned)slot >= STACK_TASK_COUNT || !size_bytes) return;
    TaskHandle_t self = xTaskGetCurrentTaskHandle();
    portENTER_CRITICAL(&mux);
    entries[slot] = (struct stack_entry){.task=self, .size_bytes=size_bytes};
    portEXIT_CRITICAL(&mux);
}

void stack_diagnostics_sample(void) {
    for (unsigned i = 0; i < STACK_TASK_COUNT; i++) {
        portENTER_CRITICAL(&mux);
        struct stack_entry entry = entries[i];
        portEXIT_CRITICAL(&mux);
        if (!entry.task) continue;
        // ESP-IDF returns bytes, not upstream FreeRTOS words. Scan outside mux.
        uint32_t free_bytes = uxTaskGetStackHighWaterMark(entry.task);
        if (free_bytes > entry.size_bytes) continue;
        portENTER_CRITICAL(&mux);
        if (entries[i].task == entry.task) {
            if (!entries[i].measured || free_bytes < entries[i].min_free_bytes)
                entries[i].min_free_bytes = free_bytes;
            entries[i].measured = true;
        }
        portEXIT_CRITICAL(&mux);
    }
}

void stack_diagnostics_add_json(cJSON *memory) {
    static const char *const names[] = {"main", "sensor", "sheets", "bosch", "cloudflare", "http"};
    struct stack_entry snapshot[STACK_TASK_COUNT];
    portENTER_CRITICAL(&mux);
    for (unsigned i = 0; i < STACK_TASK_COUNT; i++) snapshot[i] = entries[i];
    portEXIT_CRITICAL(&mux);
    cJSON *stacks = cJSON_AddObjectToObject(memory, "stacks");
    if (!stacks) return;
    for (unsigned i = 0; i < STACK_TASK_COUNT; i++) {
        if (!snapshot[i].measured) continue; // Unknown is absent, never fake zero.
        cJSON *task = cJSON_AddObjectToObject(stacks, names[i]);
        if (!task) continue;
        cJSON_AddNumberToObject(task, "size_bytes", snapshot[i].size_bytes);
        cJSON_AddNumberToObject(task, "min_free_bytes", snapshot[i].min_free_bytes);
        cJSON_AddNumberToObject(task, "peak_used_estimate_bytes",
                               snapshot[i].size_bytes - snapshot[i].min_free_bytes);
    }
}
