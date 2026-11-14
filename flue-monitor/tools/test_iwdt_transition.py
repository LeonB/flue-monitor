"""Smoke-test generated C, CPU progress gating and SDK fingerprint guards.

Race regressions live in tools/iwdt_review/run_review.py. No
device is accessed. ASan/UBSan and negative SDK fingerprint checks are included.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
from patch_iwdt_transition import EXPECTED, generate

project = Path(__file__).resolve().parents[1]
sdk = Path(os.environ.get('IDF_PATH', Path.home() / 'Library/Caches/esphome/idf/frameworks/6.0.3'))


def function(source, name):
    match = re.search(r'^.*\b' + name + r'\([^;]*?\)\s*\{', source, re.M)
    assert match, name
    end = match.end()
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define ESP_SYSTEM_IRAM_ATTR
#define CONFIG_ESP_INT_WDT 1
#define CONFIG_ESP32_ECO3_CACHE_LOCK_FIX 1
#define CONFIG_ESP_INT_WDT_CHECK_CPU1 1
#define CONFIG_ESP_INT_WDT_TIMEOUT_MS 800
#define IWDT_LIVELOCK_TIMEOUT_MS 20
#define IWDT_STAGE0_TIMEOUT_US 1600
#define IWDT_STAGE1_TIMEOUT_US 3200
#define WDT_STAGE0 0
#define WDT_STAGE1 1
#define WDT_STAGE_ACTION_INT 0
#define WDT_STAGE_ACTION_RESET_SYSTEM 1
typedef int wdt_hal_context_t;
static wdt_hal_context_t iwdt_context;
static int s_iwdt_configure_lock;
static uint32_t _lx_intr_livelock_counter, _lx_intr_livelock_max;
static volatile bool int_wdt_cpu1_ticked;
volatile uint32_t _lx_intr_livelock_sync[2], _lx_intr_livelock_app, _lx_intr_livelock_pro;
static void flue_iwdt_observe_barrier(void) {}
static uint32_t esp_cpu_get_cycle_count(void) { static uint32_t clock; return ++clock; }
static unsigned core, level, hw0, hw1, feeds, steps, inject_at, injection_kind;
static bool pending, protect, panic_seen, injected, chip_bug=true;
static bool queue_tick, run_queued_tick;
static unsigned retries, commits;
static void tick_hook(void);
static bool soc_has_cache_lock_bug(void) {return chip_bug;}
static unsigned esp_cpu_get_core_id(void) {return core;}

/* Simplified smoke-test IRQ delivery only; NOT a concurrency model.
 * The instruction-level interleavings are exercised by iwdt_review.
 */
static void recover_irq(void) {
    assert(level<4 && pending);
    if (_lx_intr_livelock_counter >= _lx_intr_livelock_max) {
        panic_seen=true; pending=false; return;
    }
    _lx_intr_livelock_counter++;
    hw0=1600/(_lx_intr_livelock_max+1); hw1=3200; feeds++;
    protect=true; pending=false;
}
static void step(void) {
    if (level>=4) return; /* Bounded commit: no newly expired long deadline. */
    steps++;
    if (!injected && inject_at==steps) {
        injected=true; pending=true;
        if (injection_kind==0) recover_irq();
        /* kind 1: other CPU has started; delivery to this CPU is delayed
         * through the initial hardware writes until high IRQs are restored.
         */
    }
}
static void portENTER_CRITICAL_SAFE(int *lock) {
    assert(!*lock && level<4); *lock=1; level=3;
}
static void portEXIT_CRITICAL_SAFE(int *lock) {
    assert(*lock && level==3); *lock=0;
    if (queue_tick) {
        queue_tick=false;run_queued_tick=true;
        core=0; int_wdt_cpu1_ticked=true; tick_hook();
    }
}
static unsigned flue_iwdt_mask_high_interrupts(void) {
    step();unsigned old=level;level=5;return old;
}
static void flue_iwdt_restore_high_interrupts(unsigned old) {
    assert(level==5 && old==3);level=old;
    if(pending) {retries++;recover_irq();}
}
static bool flue_iwdt_interrupt_pending(void) {assert(level==5);return pending;}
static uint32_t flue_iwdt_stage0_ticks(void) {assert(level==5);return hw0;}
static uint32_t flue_iwdt_stage1_ticks(void) {return hw1;}
static bool flue_iwdt_write_protect_is_open(void) {return !protect;}
static void wdt_hal_write_protect_disable(wdt_hal_context_t *c) {
    (void)c;step();protect=false;
}
static void wdt_hal_config_stage(wdt_hal_context_t *c,int stage,uint32_t ticks,int action) {
    (void)c;(void)action;step();
    if(!protect) {if(stage==0)hw0=ticks;else hw1=ticks;}
}
static void wdt_hal_feed(wdt_hal_context_t *c) {(void)c;step();if(!protect)feeds++;}
static void wdt_hal_write_protect_enable(wdt_hal_context_t *c) {(void)c;protect=true;step();}
void esp_int_wdt_reconfigure_ticks(uint32_t,uint32_t);
void esp_int_wdt_set_livelock_mode(bool);
'''

TESTS = r'''
static void reset(bool enabled) {
    core=0;level=3;hw0=enabled?40:1600;hw1=3200;feeds=0;steps=0;
    inject_at=0;injection_kind=0;pending=false;protect=true;panic_seen=false;
    injected=false;queue_tick=false;run_queued_tick=false;retries=0;commits=0;
    chip_bug=true;s_iwdt_configure_lock=0;s_flue_livelock_enabled=enabled;
    _lx_intr_livelock_counter=0;_lx_intr_livelock_max=enabled?39:0;
    int_wdt_cpu1_ticked=false;
}
int main(void) {
    reset(true);esp_int_wdt_set_livelock_mode(false);
    esp_int_wdt_set_livelock_mode(true);
    assert(hw0==40 && hw1==3200 && _lx_intr_livelock_max==39);
    /* CPU1 tick alone cannot feed; CPU0 requires the CPU1 progress flag. */
    reset(true);tick_hook();assert(feeds==0);
    core=1;tick_hook();assert(feeds==0);
    core=0;tick_hook();assert(feeds>0 && hw0==40);
    /* A CPU0 tick waiting for a CPU1 sleep transition cannot re-enable
     * the short watchdog after the mode setter releases the shared lock. */
    reset(true);core=1;queue_tick=true;esp_int_wdt_set_livelock_mode(false);
    assert(run_queued_tick && hw0==1600 && _lx_intr_livelock_max==0);
    assert(!s_flue_livelock_enabled);
    reset(false);core=0;int_wdt_cpu1_ticked=true;tick_hook();
    assert(hw0==1600 && _lx_intr_livelock_max==0);
    reset(true);chip_bug=false;esp_int_wdt_set_livelock_mode(false);
    assert(hw0==1600 && hw1==3200);
    puts("PASS restore, CPU progress gating, serialized tick/mode and non-ECO3 checks");
}
'''

with tempfile.TemporaryDirectory(prefix='flue-iwdt-test-') as directory:
    temp = Path(directory)
    generate(sdk, temp / 'generated')
    assembly_original = (sdk / 'components/esp_system/port/soc/esp32/highint_hdl.S').read_text()
    assembly_generated = (temp / 'generated/highint_hdl.S').read_text()
    for symbol in ['_lx_intr_livelock_sync', '_lx_intr_livelock_app', '_lx_intr_livelock_pro']:
        assert assembly_generated.count('.global ' + symbol + '\n') == 1
        assembly_generated = assembly_generated.replace('.global ' + symbol + '\n', '')
    assert assembly_generated == assembly_original, 'Assembly instructions changed'
    original = (sdk / 'components/esp_system/port/soc/esp32/eco3_livelock_workaround.c').read_text()
    upstream = os.environ.get('IWDT_UPSTREAM_DIR')
    if upstream:
        generated = (Path(upstream) / 'components/esp_system/int_wdt.c').read_text()
        helper = (Path(upstream) / 'components/esp_system/port/soc/esp32/eco3_livelock_workaround.c').read_text()
    else:
        generated = (temp / 'generated/int_wdt.c').read_text()
        helper = original
    functions = '\n'.join(function(original, name) for name in [
        'esp_int_wdt_reset_livelock_params', 'esp_int_wdt_set_livelock_params',
        'esp_int_wdt_livelock_get_feed_stage0_ticks'])
    functions += '\n' + '\n'.join(function(generated, name) for name in [
        'reconfigure_ticks', 'esp_int_wdt_reconfigure_ticks'])
    functions += '\n' + function(original, 'esp_int_wdt_livelock_workaround').replace(
        'esp_int_wdt_livelock_workaround', 'vulnerable')
    if upstream:
        start = generated.index('static bool s_livelock_enabled')
        end = generated.index('\n#endif', generated.index('static void ESP_SYSTEM_IRAM_ATTR iwdt_tick', start))
        functions += '\n' + generated[start:end]
        preamble = PREAMBLE.replace('flue_iwdt_', 'iwdt_')
        tests = TESTS.replace('s_flue_livelock_enabled', 's_livelock_enabled')
        functions += '\n' + function(helper, 'esp_int_wdt_livelock_workaround')
        tests = tests.replace('esp_int_wdt_set_livelock_mode(', 'esp_int_wdt_livelock_workaround(')
        # The existing public wrapper intentionally returns immediately on
        # unaffected chips; unlike the internal setter it must not feed.
        tests = tests.replace(
            'assert(hw0==1600 && hw1==3200);\n    puts',
            'assert(hw0==40 && hw1==3200 && feeds==0);\n    puts')
    else:
        functions += '\n' + (project / 'cmake/iwdt_transition.c.inc').read_text()
        preamble, tests = PREAMBLE, TESTS
    if upstream and 's_int_wdt_cpu1_idle' in generated:
        preamble += '\nstatic bool s_int_wdt_cpu1_idle;\n'
        tests = tests.replace('int_wdt_cpu1_ticked=false;',
                              'int_wdt_cpu1_ticked=false;s_int_wdt_cpu1_idle=false;')
        tests = tests.replace('    /* A CPU0 tick waiting',
                             '    reset(false);s_int_wdt_cpu1_idle=true;tick_hook();\n'
                             '    assert(feeds>0 && hw0==1600 && _lx_intr_livelock_max==0);\n'
                             '    /* A CPU0 tick waiting')
    functions += '\n' + function(generated, 'tick_hook')
    c = temp / 'test.c'
    c.write_text(preamble + functions + tests)
    binary = temp / 'test'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    if upstream:
        print('PASS extracted upstream PR functions and SDK wrapper (ASan/UBSan)')
    fake = temp / 'changed-sdk'
    for name in EXPECTED:
        p = fake / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((sdk / name).read_bytes())
    changed = fake / next(iter(EXPECTED))
    changed.write_text(changed.read_text() + '\n/* changed SDK */\n')
    try:
        generate(fake, temp / 'rejected')
    except ValueError as error:
        assert 'Unreviewed SDK source' in str(error)
    else:
        raise AssertionError('Changed SDK accepted')
    print('PASS changed SDK rejected; installed SDK unchanged')
