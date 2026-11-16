"""Run actual Sheets worker/init/upload and sensor classification with host shims."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
sheets = re.sub(r'^#include .*$', '', (root / 'main/sheets_logger.c').read_text(), flags=re.M)
sensors = (root / 'main/sensors.c').read_text()
classify = sensors[sensors.index('static thermocouple_zone_t classify_zone('):sensors.index('// Admits a new thermocouple sample')]
headers = ''.join((root / 'main' / name).read_text().replace('#pragma once', '').replace('#include "esp_err.h"', '')
                  for name in ['settings.h', 'sensors.h'])
preamble = r'''
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#define FLUE_TRACE(...) ((void)0)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <setjmp.h>
typedef int esp_err_t;
typedef void *QueueHandle_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define pdTRUE 1
#define pdPASS 1
#define tskIDLE_PRIORITY 0
#define SHEETS_STACK_BYTES 12288
#define STACK_SHEETS 2
#define pdMS_TO_TICKS(n) (n)
#define ESP_LOGD(tag,...) ((void)(tag), (void)snprintf(NULL,0,__VA_ARGS__))
#define ESP_LOGW ESP_LOGD
#define ESP_LOGI ESP_LOGD
#define ESP_LOGE ESP_LOGD
'''
shims = r'''
static int64_t clock_us=1000000000;
static bool fail_alloc,fail_queue,fail_task,fail_client,transport_error,event_mode;
static unsigned live_buffers,queues,task_creates,begins,ends,performs,cleanups,loops;
static unsigned registration;
static bool succeeded, outdoor_valid=true;
static jmp_buf stop;
static const char *reply="ok";
static char sent_url[1024];
static void *buffer_memory_calloc(size_t n,size_t size) {
 if(fail_alloc)return NULL;void *p=calloc(n,size);assert(p);live_buffers++;return p;
}
static void tracked_free(void *p) {if(p){assert(live_buffers);live_buffers--;free(p);}}
#define free tracked_free
static int64_t esp_timer_get_time(void) {return clock_us;}
static void stack_diagnostics_register(int slot,int size) {assert(slot==STACK_SHEETS && size==SHEETS_STACK_BYTES);registration++;}
void settings_get(settings_t *s) {
 memset(s,0,sizeof *s);strcpy(s->google_sheets_webhook_url,"https://example.invalid/sheets");
 strcpy(s->google_sheets_secret,"test-secret");s->thermocouple_deadband_c=0.5;s->log_heartbeat_min=5;
}
void settings_get_zone_limits(float *cold,float *optimal) {*cold=100;*optimal=250;}
void sensors_get_last_reading(sensor_reading_t *r) {*r=(sensor_reading_t){.thermocouple_ok=true,.thermocouple_c=123.4,.cold_junction_c=21.2,.thermocouple_zone=THERMOCOUPLE_ZONE_OPTIMAL};}
bool thermocouple_reading_plausible(float c) {return c>=-40 && c<=600;}
const char *thermocouple_zone_name(thermocouple_zone_t z) {(void)z;return "optimal";}
static bool bosch_client_get_temperature(double *room) {*room=19.6;return true;}
static bool bosch_client_get_outdoor_temperature(double *out) {if(!outdoor_valid)return false;*out=7.8;return true;}
static QueueHandle_t xQueueCreate(int count,size_t size) {assert(count==4 && size>0);if(fail_queue)return 0;queues++;return (void *)1;}
static void vQueueDelete(QueueHandle_t q) {assert(q && queues);queues--;}
static int xTaskCreate(void (*fn)(void *),const char *name,int size,void *arg,int priority,void *out) {
 (void)fn;(void)name;(void)arg;(void)out;assert(size==SHEETS_STACK_BYTES && priority==1);task_creates++;return fail_task?0:pdPASS;
}
static int xQueueReceive(QueueHandle_t q,void *item,int timeout);
static int xQueueSend(QueueHandle_t q,const void *item,int timeout) {(void)item;(void)timeout;assert(q);return pdTRUE;}
static void memory_diagnostics_sample(void) {}
static void memory_diagnostics_sheets_begin(void) {begins++;}
static void memory_diagnostics_sheets_end(bool ok) {ends++;succeeded=ok;}
static const char *esp_err_to_name(int e) {(void)e;return "test";}
static int esp_crt_bundle_attach(void *c) {(void)c;return 0;}
#define HTTP_EVENT_ON_CONNECTED 1
#define HTTP_EVENT_ON_DATA 2
#define HTTP_METHOD_GET 0
typedef struct {int event_id,data_len;const char *data;} esp_http_client_event_t;
typedef struct {const char *url;int method,timeout_ms,buffer_size_tx,max_redirection_count;
 int (*event_handler)(esp_http_client_event_t *);int (*crt_bundle_attach)(void *);} esp_http_client_config_t;
typedef const esp_http_client_config_t *esp_http_client_handle_t;
static esp_http_client_config_t client_config;
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg) {
 if(fail_client)return NULL;client_config=*cfg;return &client_config;
}
static int esp_http_client_perform(esp_http_client_handle_t c) {
 assert(c && c->url);performs++;snprintf(sent_url,sizeof sent_url,"%s",c->url);
 esp_http_client_event_t ev={.event_id=HTTP_EVENT_ON_CONNECTED};c->event_handler(&ev);
 ev=(esp_http_client_event_t){.event_id=HTTP_EVENT_ON_DATA,.data=reply,.data_len=(int)strlen(reply)};c->event_handler(&ev);
 return transport_error?ESP_FAIL:ESP_OK;
}
static int esp_http_client_get_status_code(esp_http_client_handle_t c) {assert(c);return 200;}
static void esp_http_client_cleanup(esp_http_client_handle_t c) {assert(c);cleanups++;}
'''
tests = r'''
static int xQueueReceive(QueueHandle_t q,void *out,int timeout) {
 assert(q && timeout==30000);if(loops++)longjmp(stop,1);
 if(!event_mode)return 0;
 queued_event_t *item=out;memset(item,0,sizeof *item);strcpy(item->label,"added_wood");
 sensors_get_last_reading(&item->reading);item->room_temperature_c=18.5;item->outdoor_temperature_c=-2.5;
 item->enqueued_us=clock_us-3000000;item->enqueued_epoch_s=1704067201;return pdTRUE;
}
static void tick(void) {loops=0;if(!setjmp(stop))sheets_logger_task(NULL);}
int main(void) {
 assert(classify_zone(100)==THERMOCOUPLE_ZONE_COLD);
 assert(classify_zone(100.1)==THERMOCOUPLE_ZONE_OPTIMAL);
 assert(classify_zone(250)==THERMOCOUPLE_ZONE_OPTIMAL);
 assert(classify_zone(250.1)==THERMOCOUPLE_ZONE_HOT);
 assert(!sheets_logger_log_event("added_wood"));
 fail_alloc=true;sheets_logger_init();assert(!s_ready && !s_buffers && !queues && !task_creates);
 fail_alloc=false;fail_queue=true;sheets_logger_init();assert(!s_ready && !s_buffers && !live_buffers && !queues);
 fail_queue=false;fail_task=true;sheets_logger_init();assert(!s_ready && !s_buffers && !live_buffers && !queues);
 assert(!sheets_logger_log_event("added_wood"));
 fail_task=false;sheets_logger_init();assert(s_ready && s_buffers && live_buffers==1 && queues==1);
 unsigned created=task_creates;sheets_logger_init();assert(task_creates==created && live_buffers==1);
 puts("PASS sensor zone boundaries; Sheets PSRAM/queue/task failures clean up and reject events; init retry succeeds");
 fail_client=true;tick();assert(!begins && !performs && s_last_logged_thermocouple_c==NO_PRIOR_LOG_C);
 fail_client=false;reply="forbidden";tick();assert(!succeeded && s_last_logged_thermocouple_c==NO_PRIOR_LOG_C);
 reply="ok";transport_error=true;tick();assert(!succeeded && s_last_logged_thermocouple_c==NO_PRIOR_LOG_C);
 transport_error=false;tick();assert(succeeded && s_last_logged_thermocouple_c>123 && s_last_log_us==clock_us);
 assert(strstr(sent_url,"outdoor_temperature=7.8") && strstr(sent_url,"room_temperature=19.6") && strstr(sent_url,"event=temp_change"));
 unsigned previous=performs;tick();assert(performs==previous); // unchanged reading must not upload
 event_mode=true;tick();assert(performs==previous+1 && succeeded);
 assert(strstr(sent_url,"event=added_wood") && strstr(sent_url,"age_ms=3000") && strstr(sent_url,"event_ts=1704067201") && strstr(sent_url,"room_temperature=18.5") && strstr(sent_url,"outdoor_temperature=-2.5"));
 event_mode=false;outdoor_valid=false;s_last_logged_thermocouple_c=NO_PRIOR_LOG_C;tick();
 assert(!strcmp(strstr(sent_url,"&outdoor_temperature="),"&outdoor_temperature="));
 assert(s_last_log_us==clock_us && begins==ends && cleanups==performs && live_buffers==1 && registration);
 vQueueDelete(s_event_queue);free(s_buffers);assert(!live_buffers && !queues);
 puts("PASS Sheets periodic/event snapshots, complete URLs, allocation/transport/rejected-response failures, unchanged retry baseline and resource lifetime");
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'sheets_test.c'
    binary = Path(directory) / 'sheets_test'
    source.write_text(preamble + headers + "\nstatic void refill_notify_send_pending(const settings_t *s) {(void)s;}\n" + shims + sheets + classify + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
