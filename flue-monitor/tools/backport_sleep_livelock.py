#!/usr/bin/env python3
"""Guarded ESP-IDF 5.5.6 backport; installed SDK remains untouched.

Based on Espressif commits d45606bf1d450924fbba25eb692ab7d7e27dee77
and 8220859330da141d860defece8aed1f414459bfa (Apache-2.0).
Only light sleep is changed. Watchdogs remain enabled; the ECO3 20-ms
workaround is suspended while the other CPU is stalled, then restored.
"""
from pathlib import Path
import hashlib
import sys

sdk, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)

def replace_once(s, old, new):
    if s.count(old) != 1:
        raise SystemExit('SDK backport guard failed: ' + old[:100])
    return s.replace(old, new, 1)

sleep = (sdk/'components/esp_hw_support/sleep_modes.c').read_text()
wdt = (sdk/'components/esp_system/int_wdt.c').read_text()
chip = (sdk/'components/esp_hw_support/port/esp32/chip_info.c').read_text()
# Whole-file guards are inserted below for the exact supported SDK release.
EXPECTED = {'sleep_modes.c': 'b2752993bc2a7a5a1ae410f1d9ec4a56051592b2b38f7095647bd948feb37929', 'int_wdt.c': '23bef7d5b1ad7dbbf08a5f5b4107e16d063ef6b57e467161fd8360c82a3bbea7', 'chip_info.c': 'e99183cd105e73cae22c8825258687ac7a665456367735da2476701bd93b3053'}
for name, source in [('sleep_modes.c',sleep), ('int_wdt.c',wdt), ('chip_info.c',chip)]:
    if name in EXPECTED and hashlib.sha256(source.encode()).hexdigest() != EXPECTED[name]:
        raise SystemExit('Unsupported SDK source: ' + name)

wdt = replace_once(wdt, '#include "freertos/FreeRTOS.h"', '#include "freertos/FreeRTOS.h"\n#include "freertos/portmacro.h"')
start = wdt.index('static void ESP_SYSTEM_IRAM_ATTR tick_hook(void)')
end = wdt.index('\nvoid esp_int_wdt_init(void)', start)
wdt = wdt[:start] + r'''
static portMUX_TYPE s_iwdt_configure_lock = portMUX_INITIALIZER_UNLOCKED;

static void IRAM_ATTR reconfigure_ticks(uint32_t stage0_ticks)
{
    wdt_hal_write_protect_disable(&iwdt_context);
    wdt_hal_config_stage(&iwdt_context, WDT_STAGE0, stage0_ticks, WDT_STAGE_ACTION_INT);
    wdt_hal_config_stage(&iwdt_context, WDT_STAGE1,
                        2 * CONFIG_ESP_INT_WDT_TIMEOUT_MS * 1000 / IWDT_TICKS_PER_US,
                        WDT_STAGE_ACTION_RESET_SYSTEM);
    wdt_hal_feed(&iwdt_context);
    wdt_hal_write_protect_enable(&iwdt_context);
}

#if CONFIG_ESP32_ECO3_CACHE_LOCK_FIX
void IRAM_ATTR esp_int_wdt_livelock_workaround(bool enable)
{
    if (!soc_has_cache_lock_bug()) {
        return;
    }
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    _lx_intr_livelock_counter = 0;
    _lx_intr_livelock_max = enable ? CONFIG_ESP_INT_WDT_TIMEOUT_MS / IWDT_LIVELOCK_TIMEOUT_MS - 1 : 0;
    reconfigure_ticks(CONFIG_ESP_INT_WDT_TIMEOUT_MS * 1000 / IWDT_TICKS_PER_US / (_lx_intr_livelock_max + 1));
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}
#endif

static void IRAM_ATTR tick_hook(void)
{
    if (esp_cpu_get_core_id() != 0) {
#if CONFIG_ESP_INT_WDT_CHECK_CPU1
        int_wdt_cpu1_ticked = true;
#endif
        return;
    }
#if CONFIG_ESP_INT_WDT_CHECK_CPU1
    if (!int_wdt_cpu1_ticked) {
        return;
    }
    int_wdt_cpu1_ticked = false;
#endif
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    uint32_t ticks = CONFIG_ESP_INT_WDT_TIMEOUT_MS * 1000 / IWDT_TICKS_PER_US;
#if CONFIG_ESP32_ECO3_CACHE_LOCK_FIX
    _lx_intr_livelock_counter = 0;
    if (soc_has_cache_lock_bug()) {
        _lx_intr_livelock_max = CONFIG_ESP_INT_WDT_TIMEOUT_MS / IWDT_LIVELOCK_TIMEOUT_MS - 1;
    }
    ticks /= (_lx_intr_livelock_max + 1);
#endif
    reconfigure_ticks(ticks);
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}
''' + wdt[end:]
chip = replace_once(chip, '#include "esp_chip_info.h"', '#include "esp_chip_info.h"\n#include "esp_attr.h"')
chip = replace_once(chip, 'inline bool soc_has_cache_lock_bug(void)', 'IRAM_ATTR inline bool soc_has_cache_lock_bug(void)')
sleep = replace_once(sleep, '#include "esp_attr.h"', '#include "esp_attr.h"\n#include <stdbool.h>\n#if CONFIG_ESP_INT_WDT && CONFIG_ESP32_ECO3_CACHE_LOCK_FIX\nvoid esp_int_wdt_livelock_workaround(bool enable);\n#endif')
# Restrict replacements to light sleep; deep sleep is deliberately unchanged.
pos = sleep.index('esp_err_t esp_light_sleep_start(void)')
head, light = sleep[:pos], sleep[pos:]
light = replace_once(light, '    esp_ipc_isr_stall_other_cpu();', '''#if CONFIG_ESP_INT_WDT && CONFIG_ESP32_ECO3_CACHE_LOCK_FIX
    // Take the WDT lock BEFORE stalling the other CPU (upstream lock order).
    esp_int_wdt_livelock_workaround(false);
#endif
    esp_ipc_isr_stall_other_cpu();''')
light = replace_once(light, '    esp_ipc_isr_release_other_cpu();', '''    esp_ipc_isr_release_other_cpu();
#if CONFIG_ESP_INT_WDT && CONFIG_ESP32_ECO3_CACHE_LOCK_FIX
    esp_int_wdt_livelock_workaround(true);
#endif''')
for name, source in [('sleep_modes.c',head+light), ('int_wdt.c',wdt), ('chip_info.c',chip)]:
    (out/name).write_text(source)
