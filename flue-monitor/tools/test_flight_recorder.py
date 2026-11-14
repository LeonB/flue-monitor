"""Execute the real recorder with deterministic IRQ/core/clock/RTC shims."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
component = root / 'components/flight_recorder'
header = re.sub(r'^#(?:include|pragma).*$', '', (component/'include/flight_recorder.h').read_text(), flags=re.M)
source = re.sub(r'^#include .*$', '', (component/'flight_recorder.c').read_text(), flags=re.M)
preamble = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define CONFIG_FLUE_DIAG_RECORDER 1
#define CONFIG_FLUE_DIAG_CRASH_TEST 0
#define COREDUMP_DRAM_ATTR
#define RTC_NOINIT_ATTR
#define IRAM_ATTR
#define MALLOC_CAP_SPIRAM 1
#define ESP_OK 0
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) (logs++)
typedef int esp_err_t;
static unsigned core,mask,logs;
static uint32_t ticks;
static unsigned portSET_INTERRUPT_MASK_FROM_ISR(void) {unsigned old=mask;mask++;return old;}
static void portCLEAR_INTERRUPT_MASK_FROM_ISR(unsigned old) {assert(mask==old+1);mask=old;}
static unsigned esp_cpu_get_core_id(void) {assert(mask);return core;}
static int64_t esp_timer_get_time(void) {return ++ticks;}
static unsigned esp_cpu_get_cycle_count(void) {return ++ticks;}
static int esp_reset_reason(void) {return 3;}
typedef esp_err_t (*sleep_cb_t)(void *,void *);
typedef struct {sleep_cb_t cb;void *user_arg;unsigned prior;} esp_sleep_event_cb_config_t;
#define SLEEP_EVENT_CB_INDEX_NUM 10
static esp_sleep_event_cb_config_t callbacks[SLEEP_EVENT_CB_INDEX_NUM];
static int esp_sleep_register_event_callback(unsigned event,const esp_sleep_event_cb_config_t *cb) {assert(!mask && event<10);callbacks[event]=*cb;return ESP_OK;}
static void (*alloc_failed)(size_t,uint32_t,const char *);
static int heap_caps_register_failed_alloc_callback(void (*cb)(size_t,uint32_t,const char *)) {assert(!mask);alloc_failed=cb;return ESP_OK;}
'''
tests = r'''
int main(void) {
 flight_recorder_init();assert(flue_trace.magic==TRACE_MAGIC && !mask);
 for(core=0;core<2;core++) {
  for(unsigned i=0;i<1000;i++)flue_trace_record(FLUE_EVT_TEST_READY,i);
  uint32_t head=flue_trace.heads[core][0];assert(head==1000+(core==0));
  for(unsigned i=0;i<96;i++) {
   uint32_t seq=head-i;volatile flue_record_t *r=&flue_trace.operations[core][(seq-1)%96];
   assert(r->sequence==seq && r->core==core && r->event==FLUE_EVT_TEST_READY && r->value==999-i && !r->flags);
  }
  for(unsigned i=0;i<100;i++)callbacks[i%10].cb(callbacks[i%10].user_arg,NULL);
  assert(flue_trace.heads[core][1]==100 && flue_trace.heads[core][0]==head);
  for(unsigned i=0;i<32;i++) {
   uint32_t seq=100-i;volatile flue_record_t *r=&flue_trace.sleep[core][(seq-1)%32];
   assert(r->sequence==seq && r->core==core && r->flags==1 && r->event==FLUE_EVT_SLEEP_BASE+(99-i)%10);
  }
 }
 core=0;alloc_failed(321,MALLOC_CAP_SPIRAM,"test");
 uint32_t head=flue_trace.heads[0][0];assert(flue_trace.operations[0][(head-1)%96].event==FLUE_EVT_ALLOC_FAIL_PSRAM);
 alloc_failed(123,0,"test");head=flue_trace.heads[0][0];assert(flue_trace.operations[0][(head-1)%96].event==FLUE_EVT_ALLOC_FAIL_INTERNAL);
 assert(!mask && !logs);memset((void *)&flue_trace,0,sizeof flue_trace);flight_recorder_init();
 assert(logs==32 && flue_trace.magic==TRACE_MAGIC && flue_trace.heads[0][0]==1);
 rtc_tail.magic=0;unsigned before=logs;flight_recorder_init();assert(logs==before);
 puts("PASS two cores, ring wrap/order/commit, isolated sleep bank, IRQ restoration, allocation failures and validated warm-reset RTC tail");
}
'''
with tempfile.TemporaryDirectory() as directory:
    c = Path(directory)/'test.c';binary=Path(directory)/'test'
    c.write_text(preamble+header+source+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-variable',
                    '-fsanitize=address,undefined',str(c),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=10)
