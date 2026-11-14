#include "flight_recorder.h"
#if CONFIG_FLUE_DIAG_RECORDER
#include <stddef.h>
#include <string.h>
#include "esp_attr.h"
#include "esp_cpu.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_private/sleep_event.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define TRACE_MAGIC 0x46545231u
COREDUMP_DRAM_ATTR volatile flue_recorder_t flue_trace;
// A small tail can survive warm resets even if panic handling never ran.
// Magic/commit validation is mandatory; power/RTC resets may destroy it.
RTC_NOINIT_ATTR static volatile struct {
    uint32_t magic, version, heads[2];
    flue_record_t records[2][16];
} rtc_tail;

static inline void IRAM_ATTR commit(volatile flue_record_t *out, uint32_t sequence,
                                   uint32_t clock, uint16_t event, unsigned core,
                                   uint8_t flags, uint32_t value) {
    out->sequence = 0;
    out->clock = clock; out->event = event; out->core = core;
    out->flags = flags; out->value = value;
#ifdef __XTENSA__
    __asm__ volatile("memw" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
    out->sequence = sequence;
}

static void IRAM_ATTR record(uint16_t event, uint32_t value, uint32_t clock, uint8_t flags) {
    // Per-core writers only. Briefly mask local interrupts; never wait for the
    // other CPU, allocate, format text, read PSRAM or acquire a spinlock here.
    unsigned saved = portSET_INTERRUPT_MASK_FROM_ISR();
    unsigned core = esp_cpu_get_core_id();
    unsigned bank = event >= FLUE_EVT_SLEEP_BASE;
    uint32_t seq = flue_trace.heads[core][bank] + 1;
    if (!seq) seq = 1;
    volatile flue_record_t *out = bank ? &flue_trace.sleep[core][(seq-1)%32]
                                             : &flue_trace.operations[core][(seq-1)%96];
    commit(out, seq, clock, event, core, flags, value);
    flue_trace.heads[core][bank] = seq;
    uint32_t tail_seq = rtc_tail.heads[core] + 1;
    if (!tail_seq) tail_seq = 1;
    commit(&rtc_tail.records[core][(tail_seq-1)%16], tail_seq, clock, event, core, flags, value);
    rtc_tail.heads[core] = tail_seq;
    portCLEAR_INTERRUPT_MASK_FROM_ISR(saved);
}

void IRAM_ATTR flue_trace_record(uint16_t event, uint32_t value) {
    record(event, value, (uint32_t)esp_timer_get_time(), 0);
}

static esp_err_t IRAM_ATTR sleep_event(void *arg, void *ext) {
    (void)ext;
    // Early wake/PLL callbacks must not depend on peripheral timer recovery.
    record(FLUE_EVT_SLEEP_BASE + (uintptr_t)arg, 0, esp_cpu_get_cycle_count(), 1);
    return ESP_OK;
}

static void allocation_failed(size_t size, uint32_t caps, const char *function) {
    (void)function;
    flue_trace_record(caps & MALLOC_CAP_SPIRAM ? FLUE_EVT_ALLOC_FAIL_PSRAM : FLUE_EVT_ALLOC_FAIL_INTERNAL, size);
}

void flight_recorder_init(void) {
    if (rtc_tail.magic == TRACE_MAGIC && rtc_tail.version == 1) {
        for (unsigned core=0; core<2; core++) {
            uint32_t head=rtc_tail.heads[core];
            uint32_t count=head<16 ? head : 16;
            for (uint32_t offset=0; offset<count; offset++) {
                uint32_t seq=head-count+offset+1;
                volatile flue_record_t *r=&rtc_tail.records[core][(seq-1)%16];
                if (r->sequence==seq && r->core==core)
                    ESP_LOGI("flight_recorder", "previous core=%u seq=%lu clock=%lu event=%u flags=%u value=%lu",
                             core,(unsigned long)seq,(unsigned long)r->clock,r->event,r->flags,(unsigned long)r->value);
            }
        }
    }
    memset((void *)&rtc_tail,0,sizeof rtc_tail);
    rtc_tail.version=1; rtc_tail.magic=TRACE_MAGIC;
    memset((void *)&flue_trace,0,sizeof flue_trace);
    flue_trace.version=1; flue_trace.magic=TRACE_MAGIC;
    FLUE_TRACE(BOOT, esp_reset_reason());
    esp_err_t err=heap_caps_register_failed_alloc_callback(allocation_failed);
    if (err!=ESP_OK) ESP_LOGW("flight_recorder","Allocation hook unavailable: %d",err);
    for (unsigned i=0;i<SLEEP_EVENT_CB_INDEX_NUM;i++) {
        esp_sleep_event_cb_config_t cb={.cb=sleep_event,.user_arg=(void *)(uintptr_t)i,.prior=100};
        err=esp_sleep_register_event_callback(i,&cb);
        if (err!=ESP_OK) ESP_LOGW("flight_recorder","Sleep callback %u unavailable: %d",i,err);
    }
}

#if !CONFIG_FLUE_DIAG_CRASH_TEST
void flight_recorder_test_start(void) {}
#endif
#endif
