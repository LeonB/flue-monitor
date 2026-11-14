"""Check actual panic-only timeout wrapper, including multi-minute overflow."""
from pathlib import Path
import re
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
source=re.sub(r'^#include .*$', '', (root/'components/flight_recorder/dump_watchdog.c').read_text(),flags=re.M)
preamble=r'''
#include <assert.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#define CONFIG_FLUE_DIAG_RECORDER 1
#define ESP_IDF_VERSION_VAL(a,b,c) ((a)*10000+(b)*100+(c))
#define ESP_IDF_VERSION ESP_IDF_VERSION_VAL(6,0,3)
#define IRAM_ATTR
#define RWDT_HAL_CONTEXT_DEFAULT() {0}
#define WDT_RWDT 1
#define WDT_STAGE0 0
#define WDT_STAGE_ACTION_RESET_RTC 2
typedef struct {int dummy;} wdt_hal_context_t;
typedef struct {int value;} panic_info_t;
static unsigned configured,feeds,real_calls;static bool protected=true;
static uint32_t hz=150000;
static uint32_t rtc_clk_slow_freq_get_hz(void) {return hz;}
static void wdt_hal_init(wdt_hal_context_t *c,int kind,int n,bool flag) {(void)c;assert(kind==1 && n==0 && !flag);}
static void wdt_hal_write_protect_disable(wdt_hal_context_t *c) {(void)c;assert(protected);protected=false;}
static void wdt_hal_feed(wdt_hal_context_t *c) {(void)c;assert(!protected);feeds++;}
static void wdt_hal_config_stage(wdt_hal_context_t *c,int stage,uint32_t ticks,int action) {
 (void)c;assert(!protected && stage==0 && action==2);
 assert(ticks==(configured%2==0 ? 600u : 10u)*hz);configured++;
}
static void wdt_hal_enable(wdt_hal_context_t *c) {(void)c;assert(!protected);}
static void wdt_hal_write_protect_enable(wdt_hal_context_t *c) {(void)c;assert(!protected);protected=true;}
void __real_esp_core_dump_write(panic_info_t *info) {assert(protected && configured%2==1 && info->value==123);real_calls++;}
'''
tests=r'''
int main(void) {
 panic_info_t info={123};__wrap_esp_core_dump_write(&info);
 hz=32768;__wrap_esp_core_dump_write(&info);
 assert(real_calls==2 && configured==4 && feeds==4 && protected);
 puts("PASS original dump called; panic-only timeout extends/restores and feeds before restoring; 150kHz/32kHz arithmetic does not overflow");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'test.c';binary=Path(directory)/'test'
    path.write_text(preamble+source+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
    # Fail closed if a later config accidentally re-enables panic-time heap
    # walking. A stopped CPU can own its lock indefinitely (observed IWDT).
    rejected=subprocess.run(['cc','-std=c11','-DCONFIG_ESP_COREDUMP_CAPTURE_DRAM=1',
                             '-c',str(path),'-o',str(binary)+'.o'],capture_output=True,text=True)
    assert rejected.returncode != 0
    assert 'Diagnostic panic capture must not walk the heap' in rejected.stderr
    print('PASS unsafe full-DRAM/heap capture rejected at compile time')
