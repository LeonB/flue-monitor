"""Run the actual RAM export/import and sensor merge code under ASan/UBSan."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
sensors=(root/'main/sensors.c').read_text();api=(root/'main/rest_api.c').read_text()
state=sensors[sensors.index('static history_sample_t *s_history;'):sensors.index('// If a device was left holding the bus')].replace('static uint32_t s_history_tick = 0;','')
reader=sensors[sensors.index('size_t sensors_get_history('):]
events=api[api.index('typedef struct {\n  const char *slug;\n  const char *label;'):api.index('static esp_err_t events_get_handler(')]
preamble=r'''
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "sensors.h"
#include "history_snapshot.h"
#include "cJSON.h"
static bool fail_alloc;
static void *buffer_memory_alloc(size_t n){return fail_alloc?NULL:malloc(n);}
static void *buffer_memory_calloc(size_t n,size_t s){return fail_alloc?NULL:calloc(n,s);}
#define s_last_reading_mutex 0
#define portMAX_DELAY 0
#define xSemaphoreTake(a,b) ((void)0)
#define xSemaphoreGive(a) ((void)0)
static int64_t uptime=100;
static int64_t esp_timer_get_time(void){return uptime*1000000;}
'''
tests=r'''
static void clear_ram(void){s_history_head=s_history_count=0;s_event_log_head=s_event_log_count=0;}
int main(void){
 s_history=calloc(SENSORS_HISTORY_CAPACITY,sizeof *s_history);assert(s_history);
 history_push((history_sample_t){20,200,1,2});history_push((history_sample_t){80,150,-1,2});
 event_log_push(EVENTS[2].slug);event_log_push(EVENTS[2].slug);
 history_snapshot_t before,after;size_t size=sizeof before;
 assert(rest_api_history_export(NULL,&size)==ESP_OK && size==6296);
 assert(rest_api_history_export(&before,&size)==ESP_OK);
 assert(before.version==2 && !before.saved_at && before.sample_count==2 && before.event_count==2);
 assert(before.samples[0].uptime_s==80 && before.samples[1].uptime_s==20);
 // Mac supplies30s elapsed across flash. No device wall clock or NTP involved.
 uptime=5;clear_ram();history_push((history_sample_t){3,140,-2,2});before.elapsed_s=30;
 assert(rest_api_history_import((const char *)&before,sizeof before)==ESP_OK);
 assert(s_history_count==3 && s_event_log_count==2);
 history_sample_t result[360];size_t n=sensors_get_history(result,360);assert(n==3);
 assert((uint32_t)(uptime-result[0].uptime_s)==110);assert((uint32_t)(uptime-result[1].uptime_s)==50);assert(result[2].uptime_s==3);
 assert((uint32_t)(uptime-s_event_log[0].uptime_s)==30);
 // Reimporting does not duplicate points, but retains genuine duplicate taps.
 assert(rest_api_history_import((const char *)&before,sizeof before)==ESP_OK);
 assert(s_history_count==3 && s_event_log_count==2);
 assert(rest_api_history_export(&after,&size)==ESP_OK && after.sample_count==3 && after.event_count==2);
 // Allocation or invalid input must leave the live graph unchanged.
 fail_alloc=true;assert(rest_api_history_import((const char *)&before,sizeof before)==ESP_ERR_NO_MEM);fail_alloc=false;
 assert(s_history_count==3 && s_event_log_count==2);
 history_snapshot_t bad=before;bad.version=99;assert(rest_api_history_import((const char *)&bad,sizeof bad)!=ESP_OK);
 bad=before;bad.sample_count=361;assert(rest_api_history_import((const char *)&bad,sizeof bad)!=ESP_OK);
 bad=before;bad.samples[0].thermocouple_c=NAN;assert(rest_api_history_import((const char *)&bad,sizeof bad)!=ESP_OK);
 bad=before;bad.events[0].event_id=99;assert(rest_api_history_import((const char *)&bad,sizeof bad)!=ESP_OK);
 bad=before;bad.samples[1].uptime_s=90;assert(rest_api_history_import((const char *)&bad,sizeof bad)!=ESP_OK);
 bad=before;bad.samples[0].uptime_s=UINT32_MAX;assert(rest_api_history_import((const char *)&bad,sizeof bad)!=ESP_OK);
 assert(rest_api_history_import("{}",2)!=ESP_OK && s_history_count==3);
 // Bounded merge retains the newest360 with overlapping timestamps deduplicated.
 clear_ram();history_sample_t many[360];for(unsigned i=0;i<360;i++)many[i]=(history_sample_t){i,100+(i%100),0,1};
 for(unsigned i=300;i<400;i++)history_push((history_sample_t){i,100+(i%100),0,1});
 assert(sensors_merge_history(many,360,400)==ESP_OK);n=sensors_get_history(result,360);assert(n==360 && result[0].uptime_s==40 && result[359].uptime_s==399);
 free(s_history);puts("PASS RAM export/import, Mac elapsed time without NTP, reboot/fresh merge, repeated restore, duplicate taps, bounded ring, invalid input and allocation failure");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)
 (p/'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n#define ESP_ERR_INVALID_ARG 1\n#define ESP_ERR_INVALID_STATE 2\n#define ESP_ERR_NO_MEM 3\n#define ESP_ERR_INVALID_SIZE 5\n')
 (p/'test.c').write_text(preamble+state+reader+events+tests)
 cjson=root/'managed_components/espressif__cjson/cJSON'
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-deprecated-declarations','-fsanitize=address,undefined','-I'+str(p),'-I'+str(root/'main'),'-I'+str(cjson),str(p/'test.c'),str(cjson/'cJSON.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
