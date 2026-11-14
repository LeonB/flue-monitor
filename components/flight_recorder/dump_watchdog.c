#include "sdkconfig.h"
#if CONFIG_FLUE_DIAG_RECORDER
#if CONFIG_ESP_COREDUMP_CAPTURE_DRAM
#error Diagnostic panic capture must not walk the heap: halted CPUs may hold heap locks
#endif
#include <stdint.h>
#include "esp_attr.h"
#include "esp_idf_version.h"
#include "esp_private/panic_internal.h"
#include "soc/rtc.h"
#include "hal/wdt_hal.h"

// ESP-IDF 6.0.3 arms a 10-second RTC watchdog in panic handling. Task-stack
// dumps at 115200 baud can exceed that. Extend ONLY the dump interval, with
// a bounded timeout; do not change or disable the operating IWDT/TWDT.
// These private SDK symbols must be reviewed when upgrading ESP-IDF.
#if ESP_IDF_VERSION != ESP_IDF_VERSION_VAL(6,0,3)
#error Review panic watchdog wrapper against the selected ESP-IDF version
#endif
void __real_esp_core_dump_write(panic_info_t *info);

static void IRAM_ATTR dump_timeout(uint32_t milliseconds) {
    wdt_hal_context_t ctx = RWDT_HAL_CONTEXT_DEFAULT();
    wdt_hal_init(&ctx,WDT_RWDT,0,false);
    // Cast BEFORE multiplication: the SDK helper's 32-bit multiplication
    // overflows for a multi-minute timeout at the 150-kHz slow clock.
    uint32_t ticks=(uint32_t)((uint64_t)milliseconds*rtc_clk_slow_freq_get_hz()/1000);
    wdt_hal_write_protect_disable(&ctx);
    wdt_hal_feed(&ctx);
    wdt_hal_config_stage(&ctx,WDT_STAGE0,ticks,WDT_STAGE_ACTION_RESET_RTC);
    wdt_hal_enable(&ctx);
    wdt_hal_write_protect_enable(&ctx);
}

void IRAM_ATTR __wrap_esp_core_dump_write(panic_info_t *info) {
    dump_timeout(600000);
    __real_esp_core_dump_write(info);
    dump_timeout(10000);
}
#endif
