"""Verify the actual queued WS payload ownership under allocation/send failures."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'main/ws_server.c').read_text()
core = source[source.index('typedef struct {'):source.index('void ws_server_broadcast_reading(')]
preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef int esp_err_t;
#define ESP_OK 0
#define HTTPD_WS_CLIENT_WEBSOCKET 1
#define HTTPD_WS_TYPE_TEXT 1
#define WS_MAX_CLIENTS 8
#define portMAX_DELAY 0
#define ESP_LOGW(...) ((void)0)
static void *s_server=(void*)1;
static int s_clients_mutex, s_client_count=1, s_client_fds[]={5};
static uint32_t s_client_generations[]={42};
static int allocations, live, fail_at, queue_fail, send_fail, removed, sends;
static void *queued;
static void (*callback)(void *);
static void *buffer_memory_alloc(size_t size) {
 if(++allocations==fail_at)return NULL;
 void *p=malloc(size);assert(p);live++;return p;
}
static void release(void *p){if(p){assert(live>0);live--;free(p);}}
#define free release
static void xSemaphoreTake(int a,int b){(void)a;(void)b;}
static void xSemaphoreGive(int a){(void)a;}
static int httpd_ws_get_fd_info(void *s,int fd){(void)s;(void)fd;return 1;}
typedef struct {int type;uint8_t *payload;size_t len;} httpd_ws_frame_t;
static int httpd_ws_send_frame_async(void *s,int fd,httpd_ws_frame_t *f){
 (void)s;assert(fd==5);assert(f->len==7 && !strcmp((char*)f->payload,"payload"));sends++;return send_fail;
}
static void httpd_sess_update_lru_counter(void *s,int fd){(void)s;(void)fd;}
static void clients_remove(int fd){assert(fd==5);removed++;}
static int httpd_queue_work(void *s,void (*cb)(void*),void *arg){
 (void)s;if(queue_fail)return -1;assert(!queued);queued=arg;callback=cb;return 0;
}
'''
tests = r'''
static void complete(void){assert(queued);void *p=queued;queued=NULL;callback(p);assert(!live);}
int main(void){
 broadcast_raw(NULL);assert(!allocations);
 for(int failure=1;failure<=2;failure++){
  allocations=0;fail_at=failure;broadcast_raw("payload");assert(!live && !queued);
 }
 fail_at=0;queue_fail=1;broadcast_raw("payload");assert(!live && !queued);
 queue_fail=0;char input[]="payload";broadcast_raw(input);memset(input,'x',7);assert(live==2);complete();assert(sends==1);
 broadcast_raw("payload");s_client_generations[0]++;complete();assert(sends==1);
 send_fail=1;broadcast_raw("payload");complete();assert(sends==2 && removed==1);
 puts("PASS WS payload copy, both allocation failures, queue/send failure, stale session and null JSON cleanup");
}
'''
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    code = tmp / 'test.c'
    code.write_text(preamble + core + tests)
    binary = tmp / 'test'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(code), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
