"""Host checks of the actual Cloudflare callback policy and worker lifecycle."""
from pathlib import Path
import re
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
source = re.sub(r'^#include .*$', '', (root / 'main/cloudflare_tunnel.c').read_text(), flags=re.M)
header = (root / 'main/cloudflare_tunnel.h').read_text().replace('#pragma once', '')
settings = (root / 'main/settings.h').read_text().replace('#pragma once', '').replace('#include "esp_err.h"', '')
preamble = r'''
#define _DARWIN_C_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdio.h>
#include <time.h>
#include <setjmp.h>
#include "cf_tunnel.h"
#include "cloudflare_policy.h"
typedef int esp_err_t;
typedef void *TaskHandle_t;
typedef int SemaphoreHandle_t;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
#define portMAX_DELAY 0xffffffffU
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define STACK_CLOUDFLARE 1
#define CLOUDFLARE_STACK_BYTES 12288
#define CONFIG_IDF_TARGET "esp32"
#define ESP_MAC_BASE 1
#define ESP_LOGW(...) ((void)0)
static jmp_buf done;
static int run_count, free_count, stop_count, scenario, creates;
static int64_t clock_us=100;
static int64_t esp_timer_get_time(void){return clock_us;}
static void (*created_task)(void *);
static int xSemaphoreCreateMutex(void){return 1;}
static void xSemaphoreTake(int m,unsigned wait){(void)m;(void)wait;}
static void xSemaphoreGive(int m){(void)m;}
static int xTaskCreate(void (*fn)(void *),const char *n,unsigned bytes,void *arg,int priority,TaskHandle_t *handle){(void)n;(void)arg;(void)priority;assert(bytes==12288);*handle=(void *)1;created_task=fn;creates++;return pdPASS;}
static void xTaskNotifyGive(TaskHandle_t h){assert(h);}
static unsigned ulTaskNotifyTake(int clear,unsigned timeout){(void)clear;if(timeout==portMAX_DELAY)longjmp(done,1);return 0;}
static void vTaskSuspend(void *p){(void)p;longjmp(done,2);}
static void stack_diagnostics_register(int slot,unsigned bytes){assert(slot==1 && bytes==12288);}
static void esp_read_mac(uint8_t *out,int type){(void)type;memset(out,0x42,6);}
static void *buffer_memory_calloc(size_t n,size_t size){return calloc(n,size);}
struct cft_tunnel { int dummy; };
struct cft_stream {int response;char service[40];const char *type;cft_stream_handlers_t handlers;void *ctx;bool paused;};
static const cft_transport_ops_t cft_transport_esp={0};
static bool rest_api_tunnel_font(cft_stream_t *s,const char *uri){(void)s;(void)uri;return false;}
static const char *cft_stream_header_impl(const cft_stream_t *s,const char *name){assert(!strcmp(name,"content-type"));return s->type;}
const char *cft_stream_header(const cft_stream_t *s,const char *name){return cft_stream_header_impl(s,name);}
int cft_stream_respond(cft_stream_t *s,int code,const char *type,const void *body,size_t n){(void)type;assert(strlen(body)==n);s->response=code;return 0;}
int cft_stream_proxy(cft_stream_t *s,const char *service){strcpy(s->service,service);return 0;}
bool cft_stream_proxy_available(cft_stream_t *s){(void)s;return true;}
void cft_stream_set_handlers(cft_stream_t *s,const cft_stream_handlers_t *h,void *ctx){s->handlers=*h;s->ctx=ctx;}
void cft_stream_pause_body(cft_stream_t *s,bool pause){s->paused=pause;}

'''
test = r'''
static cloudflare_settings_t saved;
void settings_get_cloudflare(cloudflare_settings_t *out){*out=saved;}
void cloudflare_tunnel_start(void);
static void on_poll(void *);
cft_tunnel_t *cft_tunnel_new(const cft_tunnel_config_t *c,const cft_transport_ops_t *t){
 assert(t==&cft_transport_esp && !c->use_ingress_rules && c->max_origin_connections==4 && c->max_concurrent_streams==16);
 assert(c->proxy_buffer_size==4096 && c->stream_window==4096 && c->num_connections==saved.connections);
 if(scenario==2){scenario=0;saved.enabled=0;cloudflare_tunnel_start();}
 return calloc(1,sizeof(cft_tunnel_t));
}
void cft_tunnel_free(cft_tunnel_t *t){free_count++;free(t);}
void cft_tunnel_request_stop(cft_tunnel_t *t,uint32_t timeout){assert(t && timeout==3000);stop_count++;}
void cft_tunnel_run(cft_tunnel_t *t){assert(t);run_count++;saved.enabled=0;cloudflare_tunnel_start();assert(!stop_count);on_poll(NULL);assert(!stop_count);clock_us+=1000000;on_poll(NULL);assert(stop_count==1);}
'''
main = r'''
int main(void){
 (void)TAG;
 assert(cloudflare_route_allowed("GET","/dashboard.js?v=valid",false));
 assert(cloudflare_route_allowed("POST","/api/settings",false));
 const char *blocked[]={"/ota","/ws","/api/wifi","/api/tunnel/settings","/api/cloudflare/status/..","/api/settings/../wifi","/%2fota"};
 for(size_t i=0;i<sizeof blocked/sizeof blocked[0];i++)assert(!cloudflare_route_allowed("GET",blocked[i],false));
 assert(!cloudflare_route_allowed("DELETE","/api/settings",false));assert(!cloudflare_route_allowed("GET","/",true));
 strcpy(saved.hostname,"cf-test.example.nl");strcpy(saved.token,"test-token");saved.enabled=1;saved.connections=4;
 cft_request_t req={.method="GET",.path="/dashboard.js?v=asset",.authority=saved.hostname,.scheme="https"};
 cft_stream_t stream={0};on_request(&saved,&stream,&req);assert(!strcmp(stream.service,"http://127.0.0.1:80"));
 stream=(cft_stream_t){0};req.authority="localhost";on_request(&saved,&stream,&req);assert(stream.response==403);
 req.authority=saved.hostname;req.scheme="http";on_request(&saved,&stream,&req);assert(stream.response==403);
 req.scheme="https";req.path="/ota";on_request(&saved,&stream,&req);assert(stream.response==404);
 req.path="/api/settings";req.method="POST";req.content_length=8192;stream.type="application/json";on_request(&saved,&stream,&req);assert(stream.response==400);
 req.content_length=4000;stream.type="text/plain";on_request(&saved,&stream,&req);assert(stream.response==400);
 stream=(cft_stream_t){.type="application/json; charset=utf-8"};on_request(&saved,&stream,&req);assert(*stream.service);
 set_state(CLOUDFLARE_STATUS_CONNECTING,4);
 for(int i=0;i<4;i++){cft_event_t e={.type=CFT_EVENT_REGISTERED,.conn_index=i};on_event(NULL,&e);}
 cloudflare_status_t status;cloudflare_tunnel_get_status(&status);assert(status.connections==4 && status.state==CLOUDFLARE_STATUS_CONNECTED);
 cft_event_t closed={.type=CFT_EVENT_CLOSED,.conn_index=1};on_event(NULL,&closed);cloudflare_tunnel_get_status(&status);assert(status.connections==3);
 cloudflare_tunnel_start();assert(creates==1 && created_task);
 if(!setjmp(done))created_task(NULL);
 assert(run_count==1 && free_count==1 && stop_count==1 && !active);
 saved.enabled=1;scenario=2;
 if(!setjmp(done))created_task(NULL);
 assert(run_count==1 && free_count==2 && stop_count==1 && !active && creates==1);
 puts("PASS: route/query allowlist, fixed loopback origin, HTTPS/Host/body checks, four-connection status, graceful config restart and config/publication race cleanup");
}
'''
# The settings getter must be declared before the extracted implementation.
with tempfile.TemporaryDirectory() as directory:
    tmp=Path(directory);c=tmp/'test.c';binary=tmp/'test'
    c.write_text(preamble+settings+header+test+'\n#include "cloudflare_queue.h"\n'+source+main)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
        '-fsanitize=address,undefined','-I'+str(root/'main'),
        '-I'+str(root/'components/esp_cf_tunnel/include'),str(c),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=10)
