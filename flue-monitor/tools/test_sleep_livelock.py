#!/usr/bin/env python3
"""Compile the actual generated watchdog functions against a register stub."""
from pathlib import Path
import subprocess
import sys
import tempfile

sdk=Path(sys.argv[1])
generator=Path(__file__).with_name('backport_sleep_livelock.py')
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    out=root/'generated'
    subprocess.run([sys.executable,str(generator),str(sdk),str(out)],check=True)
    source=(out/'int_wdt.c').read_text()
    functions=source[source.index('static portMUX_TYPE s_iwdt_configure_lock'):source.index('\nvoid esp_int_wdt_init(void)')]
    prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define IRAM_ATTR
#define CONFIG_ESP_INT_WDT_TIMEOUT_MS 800
#define CONFIG_ESP_INT_WDT_CHECK_CPU1 1
#define CONFIG_ESP32_ECO3_CACHE_LOCK_FIX 1
#define IWDT_LIVELOCK_TIMEOUT_MS 20
#define IWDT_TICKS_PER_US 500
#define WDT_STAGE0 0
#define WDT_STAGE1 1
#define WDT_STAGE_ACTION_INT 1
#define WDT_STAGE_ACTION_RESET_SYSTEM 2
#define portMUX_INITIALIZER_UNLOCKED 0
typedef int portMUX_TYPE;
static int iwdt_context, core, locks, feeds, protected=1;
static uint32_t stages[2], actions[2];
static uint32_t _lx_intr_livelock_counter, _lx_intr_livelock_max=39;
static bool int_wdt_cpu1_ticked;
static bool soc_has_cache_lock_bug(void) { return true; }
static int esp_cpu_get_core_id(void) { return core; }
#define portENTER_CRITICAL_SAFE(p) do { (void)(p); assert(locks==0); locks++; } while(0)
#define portEXIT_CRITICAL_SAFE(p) do { (void)(p); assert(locks==1); locks--; } while(0)
static void wdt_hal_write_protect_disable(int *p) { (void)p; assert(locks==1); protected=0; }
static void wdt_hal_config_stage(int *p,int stage,uint32_t ticks,int action) {
    (void)p; assert(!protected && locks==1); stages[stage]=ticks; actions[stage]=action;
}
static void wdt_hal_feed(int *p) { (void)p; assert(!protected); feeds++; }
static void wdt_hal_write_protect_enable(int *p) { (void)p; protected=1; }
'''
    test=r'''
int main(void) {
    core=0; tick_hook(); assert(feeds==0); // Must observe both cores.
    core=1; tick_hook(); assert(feeds==0);
    core=0; tick_hook(); assert(feeds==1 && stages[0]==40 && stages[1]==3200);
    assert(actions[0]==WDT_STAGE_ACTION_INT && actions[1]==WDT_STAGE_ACTION_RESET_SYSTEM);
    esp_int_wdt_livelock_workaround(false);
    assert(_lx_intr_livelock_max==0 && stages[0]==1600 && stages[1]==3200);
    assert(protected && locks==0);
    esp_int_wdt_livelock_workaround(true);
    assert(_lx_intr_livelock_max==39 && stages[0]==40 && stages[1]==3200);
    assert(protected && locks==0);
    int old=feeds; core=0; tick_hook(); assert(feeds==old);
    core=1; tick_hook(); core=0; tick_hook(); assert(feeds==old+1);
}
'''
    c=root/'test.c';c.write_text(prefix+functions+test)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test')],check=True)
    # A changed SDK must fail closed rather than silently patching new code.
    for rel in ['components/esp_hw_support/sleep_modes.c','components/esp_system/int_wdt.c','components/esp_hw_support/port/esp32/chip_info.c']:
        p=root/'changed'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((sdk/rel).read_bytes())
    p=root/'changed/components/esp_system/int_wdt.c';p.write_text(p.read_text()+'\n// changed SDK\n')
    result=subprocess.run([sys.executable,str(generator),str(root/'changed'),str(root/'rejected')],capture_output=True,text=True)
    assert result.returncode and 'Unsupported SDK source' in result.stderr
print('PASS: both-core feeding, sleep/awake timeouts, reset stage, locking, SDK guards')
