#include "sleep_diagnostics.h"
#include <stdint.h>
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_cpu.h"
#include "esp_private/sleep_event.h"

// No logging, allocation, locks, or RTC-bus accesses in sleep callbacks:
// caches/other CPU may be stopped. DRAM no-init may survive warm resets;
// treat it as evidence only when its magic survives and reset wasn't power-on.
#define TRACE_MAGIC 0x534c5032u
static __NOINIT_ATTR volatile struct {
    uint32_t magic, phase, entered, timed, clocks_ready, completed, wake_mask, reject_mask, core;
} trace;
static volatile bool clock_restore_active;

void IRAM_ATTR flue_sleep_trace_mark(uint32_t stage) {
    if (stage == 40) clock_restore_active = true;
    if (stage == 41) clock_restore_active = false;
    trace.phase = stage;
    trace.core = esp_cpu_get_core_id();
}

void IRAM_ATTR flue_sleep_clock_trace_mark(uint32_t stage) {
    if (clock_restore_active) flue_sleep_trace_mark(stage);
}

uint32_t __real_rtc_sleep_start(uint32_t wakeup, uint32_t reject);
uint32_t IRAM_ATTR __wrap_rtc_sleep_start(uint32_t wakeup, uint32_t reject) {
    trace.wake_mask = wakeup;
    trace.reject_mask = reject;
    trace.phase = 5; // Entering the ESP32 RTC hardware sleep routine.
    uint32_t result = __real_rtc_sleep_start(wakeup, reject);
    trace.phase = 6; // Hardware sleep routine returned.
    return result;
}

static esp_err_t IRAM_ATTR mark_phase(void *arg, void *unused) {
    (void)unused;
    uint32_t phase = (uint32_t)(uintptr_t)arg;
    trace.phase = phase;
    trace.core = esp_cpu_get_core_id();
    if (phase == SLEEP_EVENT_SW_GOTO_SLEEP) trace.entered++;
    if (phase == SLEEP_EVENT_HW_TIME_START) trace.timed++;
    if (phase == SLEEP_EVENT_SW_CLK_READY) trace.clocks_ready++;
    if (phase == SLEEP_EVENT_SW_EXIT_SLEEP) trace.completed++;
    return ESP_OK;
}

void sleep_diagnostics_log(void) {
    ESP_LOGI("sleep_trace", "phase=%lu core=%lu entered=%lu timed=%lu clocks=%lu completed=%lu wake=0x%lx reject=0x%lx",
             (unsigned long)trace.phase, (unsigned long)trace.core, (unsigned long)trace.entered,
             (unsigned long)trace.timed, (unsigned long)trace.clocks_ready,
             (unsigned long)trace.completed, (unsigned long)trace.wake_mask,
             (unsigned long)trace.reject_mask);
}

void sleep_diagnostics_init(void) {
    if (esp_reset_reason() != ESP_RST_POWERON && trace.magic == TRACE_MAGIC) {
        ESP_LOGW("sleep_trace", "Previous boot breadcrumb, reset_reason=%d", esp_reset_reason());
        sleep_diagnostics_log();
    }
    trace.magic = TRACE_MAGIC;
    trace.phase = UINT32_MAX;
    trace.entered = trace.timed = trace.clocks_ready = trace.completed = 0;
    trace.wake_mask = trace.reject_mask = 0;
    const esp_sleep_event_cb_index_t phases[] = {
        SLEEP_EVENT_SW_GOTO_SLEEP, SLEEP_EVENT_HW_TIME_START,
        SLEEP_EVENT_SW_CLK_READY, SLEEP_EVENT_SW_EXIT_SLEEP,
    };
    for (unsigned i = 0; i < sizeof(phases) / sizeof(phases[0]); i++) {
        esp_sleep_event_cb_config_t cb = {
            .cb = mark_phase, .user_arg = (void *)(uintptr_t)phases[i], .prior = 0,
        };
        ESP_ERROR_CHECK(esp_sleep_register_event_callback(phases[i], &cb));
    }
    ESP_LOGI("sleep_trace", "Phases: enter=3 timing=4 RTC_start=5 RTC_return=6 clocks_ready=1 complete=2");
}
