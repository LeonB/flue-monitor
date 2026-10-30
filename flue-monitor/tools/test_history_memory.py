"""Run the actual history response with a full ring and PSRAM allocator hooks."""
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
idf = Path(json.loads((root / 'build/project_description.json').read_text())['idf_path'])
cjson = root / 'managed_components/espressif__cjson/cJSON'
if not cjson.exists():
    cjson = idf / 'components/json/cJSON'
api = (root / 'main/rest_api.c').read_text()
handler = api[api.index('static esp_err_t history_get_handler('):api.index('static const httpd_uri_t history_get_uri')]
sensors_header = (root / 'main/sensors.h').read_text().replace('#pragma once', '').replace('#include "esp_err.h"', '')
events = api[api.index('#define EVENT_LOG_CAPACITY'):api.index('static void event_log_push')]
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / 'esp_heap_caps.h').write_text('''#pragma once
#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_INTERNAL 2
#define MALLOC_CAP_8BIT 4
void *heap_caps_malloc_prefer(size_t, size_t, ...);
void *heap_caps_calloc_prefer(size_t, size_t, size_t, ...);
''')
    preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#include <stdarg.h>
#include "cJSON.h"
#include "buffer_memory.h"
typedef int esp_err_t;
#define ESP_FAIL -1
#define ESP_OK 0
static size_t live, allocations;
static bool fail_alloc, denied;
void *heap_caps_malloc_prefer(size_t size,size_t choices,...) {
 va_list a;va_start(a,choices);assert(choices==2);
 assert(va_arg(a,int)==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
 assert(va_arg(a,int)==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));va_end(a);
 if(fail_alloc)return NULL;
 void *p=malloc(size);assert(p);live++;allocations++;return p;
}
static void release(void *p) {if(p){assert(live);live--;free(p);}}
#define free release
typedef struct {int status;bool send_fail;char *response;} httpd_req_t;
static bool auth_required(httpd_req_t *r){if(denied)r->status=401;return denied;}
static int64_t esp_timer_get_time(void){return 100000000000LL;}
static int httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);return 0;}
static int httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;return 0;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){
 r->response=strdup(s);if(!r->status)r->status=200;return r->send_fail?-1:0;
}
static double round_to(double a,double b){return round(a/b)*b;}
'''
    fixture = r'''
size_t sensors_get_history(history_sample_t *out,size_t n){
 assert(n==360);
 for(size_t i=0;i<n;i++)out[i]=(history_sample_t){.uptime_s=1000+i*240,.thermocouple_c=20+i/2.0f,.thermocouple_rate_c_per_min=1,.thermocouple_zone=THERMOCOUPLE_ZONE_OPTIMAL};
 return n;
}
'''
    tests = r'''
int main(void){
 cJSON_Hooks hooks={.malloc_fn=buffer_memory_alloc,.free_fn=release};cJSON_InitHooks(&hooks);
 s_event_log_count=64;s_event_log_head=0;
 for(size_t i=0;i<64;i++)s_event_log[i]=(logged_event_t){.uptime_s=90000+i,.slug="added_wood"};
 httpd_req_t r={0};assert(history_get_handler(&r)==ESP_OK && r.status==200 && live==0);
 assert(allocations>1800);
 cJSON *result=cJSON_Parse(r.response);assert(result);
 cJSON *points=cJSON_GetObjectItem(result,"samples");assert(cJSON_GetArraySize(points)==360);
 assert(cJSON_GetArraySize(cJSON_GetObjectItem(result,"events"))==64);
 assert(cJSON_GetArrayItem(cJSON_GetArrayItem(points,0),1)->valuedouble==20);
 assert(cJSON_GetArrayItem(cJSON_GetArrayItem(points,359),1)->valuedouble==199.5);
 cJSON_Delete(result);assert(live==0);release(NULL);
#undef free
 free(r.response);
 r=(httpd_req_t){.send_fail=true};history_get_handler(&r);assert(live==0);free(r.response);
 fail_alloc=true;r=(httpd_req_t){0};history_get_handler(&r);assert(r.status==503 && live==0);free(r.response);
 fail_alloc=false;denied=true;r=(httpd_req_t){0};size_t before=allocations;
 assert(history_get_handler(&r)==ESP_FAIL && r.status==401 && allocations==before);
 puts("PASS full 360-point/64-event history, PSRAM JSON hooks, response cleanup, exhausted-buffer 503 and authentication");
}
'''
    source = tmp / 'history.c'
    source.write_text(preamble + sensors_header + fixture + events + handler + tests)
    executable = tmp / 'history'
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations', '-fsanitize=address,undefined',
                    '-I', str(tmp), '-I', str(cjson), '-I', str(root.parent / 'components/captive_portal/include'),
                    str(source), str(cjson / 'cJSON.c'), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=20)
