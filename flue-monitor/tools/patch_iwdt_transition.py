"""Generate project-local SDK sources; never modify the installed ESP-IDF."""
import argparse
import hashlib
from pathlib import Path

EXPECTED = {
    'components/esp_system/int_wdt.c': '1436008ecec4a0239554467a32468a12aac80f35e2db0d34b2a07ee72711ec3d',
    'components/esp_system/port/soc/esp32/eco3_livelock_workaround.c': '8b018b65198275a1d7e8207a68fa7b0d572adfb33c5c40ffc8f44238320c02d4',
    'components/esp_system/port/soc/esp32/highint_hdl.S': '4ca8721ffb39d3e03febf5573d019bddb146680fd463f26dfaa18dd523853bb4',
}

PORT = r'''
#include "soc/timer_group_reg.h"
#include <stdlib.h>
static inline __attribute__((always_inline)) void flue_iwdt_observe_barrier(void)
{
    __asm__ __volatile__("memw" ::: "memory");
}
static inline __attribute__((always_inline)) unsigned flue_iwdt_mask_high_interrupts(void)
{
    unsigned ps;
    __asm__ __volatile__("rsil %0, 5; memw" : "=a"(ps) :: "memory");
    return ps;
}
static inline __attribute__((always_inline)) void flue_iwdt_restore_high_interrupts(unsigned ps)
{
    __asm__ __volatile__("memw; wsr %0, ps; rsync" :: "a"(ps) : "memory");
}
static inline __attribute__((always_inline)) bool flue_iwdt_interrupt_pending(void)
{
    return (REG_READ(TIMG_INT_RAW_TIMERS_REG(1)) & TIMG_WDT_INT_RAW) != 0;
}
static inline __attribute__((always_inline)) uint32_t flue_iwdt_stage0_ticks(void)
{
    return REG_READ(TIMG_WDTCONFIG2_REG(1));
}
static inline __attribute__((always_inline)) uint32_t flue_iwdt_stage1_ticks(void)
{
    return REG_READ(TIMG_WDTCONFIG3_REG(1));
}
static inline __attribute__((always_inline)) bool flue_iwdt_write_protect_is_open(void)
{
    return REG_READ(TIMG_WDTWPROTECT_REG(1)) == TIMG_WDT_WKEY_VALUE;
}

'''


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('SDK structure changed; refusing IWDT patch')
    return source.replace(old, new, 1)


def generate(sdk, output):
    inputs = {}
    for name, expected in EXPECTED.items():
        data = (sdk / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Unreviewed SDK source: {name}; refusing IWDT patch')
        inputs[Path(name).name] = data.decode()
    body = (Path(__file__).resolve().parents[1] / 'cmake/iwdt_transition.c.inc').read_text()
    source = inputs['int_wdt.c']
    anchor = '#if CONFIG_ESP_INT_WDT_CHECK_CPU1\nvolatile bool int_wdt_cpu1_ticked = false;'
    source = replace_once(source, anchor,
        '#if CONFIG_ESP_INT_WDT && CONFIG_ESP32_ECO3_CACHE_LOCK_FIX\n' + PORT + body + '\n#endif\n\n' + anchor)
    source = replace_once(source,
        '    esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);\n'
        '    esp_int_wdt_reconfigure_ticks(esp_int_wdt_livelock_get_feed_stage0_ticks(), IWDT_STAGE1_TIMEOUT_US);',
        '    flue_iwdt_tick();')
    helper = inputs['eco3_livelock_workaround.c']
    begin = helper.index('    uint32_t stage0_ticks = IWDT_STAGE0_TIMEOUT_US;')
    end = helper.index('\n}', begin)
    helper = helper[:begin] + '    esp_int_wdt_set_livelock_mode(enable);' + helper[end:]
    helper = replace_once(helper, 'void ESP_SYSTEM_IRAM_ATTR esp_int_wdt_livelock_workaround(bool enable)',
        'void esp_int_wdt_set_livelock_mode(bool enable);\n\n'
        'void ESP_SYSTEM_IRAM_ATTR esp_int_wdt_livelock_workaround(bool enable)')
    assembly = inputs['highint_hdl.S']
    for symbol in ['_lx_intr_livelock_sync', '_lx_intr_livelock_app', '_lx_intr_livelock_pro']:
        assembly = replace_once(assembly, symbol + ':', '.global ' + symbol + '\n' + symbol + ':')
    output.mkdir(parents=True, exist_ok=True)
    for name, text in [('int_wdt.c', source), ('eco3_livelock_workaround.c', helper), ('highint_hdl.S', assembly)]:
        target = output / name
        if not target.exists() or target.read_text() != text:
            target.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--idf', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    generate(args.idf, args.output)
