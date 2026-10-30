"""Exercise the actual receive callback and rediscovery helper with host stubs."""
from pathlib import Path
import subprocess
import tempfile

src = (Path(__file__).resolve().parents[1] / 'main/flue_poll.c').read_text()
callback = src[src.index('static void ws_event_handler('):src.index('// Resolves the sidecar (retrying')]
recover = src[src.index('static bool rediscover_monitor('):src.index('static void settings_task(')]
shim = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define WS_MSG_BUF_SIZE 2048
#define URL_BUF_SIZE 64
#define WEBSOCKET_EVENT_CONNECTED 1
#define WEBSOCKET_EVENT_DISCONNECTED 2
#define WEBSOCKET_EVENT_DATA 3
#define IPSTR "%u"
#define IP2STR(p) ((p)->addr)
typedef int esp_err_t;
typedef int esp_event_base_t;
typedef struct { unsigned addr; } esp_ip4_addr_t;
typedef struct {int op_code, data_len, payload_offset, payload_len; const char *data_ptr;} esp_websocket_event_data_t;
static char s_ws_msg_buf[WS_MSG_BUF_SIZE];
static int s_ws_msg_len, s_refetch_settings_sem, s_ws_client;
static bool s_ws_started = true;
static int delivered, length, stopped, started, set, order;
static bool dns_ok = true;
static int stop_result, start_result;
static char uri[64];
static void xSemaphoreGive(int s) {(void)s;}
static void handle_ws_message(const char *s,int n) {assert(s[n]==0); delivered++;length=n;}
static bool resolve_sidecar(esp_ip4_addr_t *ip) {ip->addr=42;return dns_ok;}
static int esp_websocket_client_stop(int c) {(void)c;stopped++;assert(order==0);order=1;return stop_result;}
static int esp_websocket_client_set_uri(int c,const char *s) {(void)c;assert(!s_ws_started);set++;order=2;strcpy(uri,s);return 0;}
static int esp_websocket_client_start(int c) {(void)c;assert(order==2);started++;return start_result;}
'''
test = r'''
static void frame(const char *s,int n,int offset,int total) {
 esp_websocket_event_data_t e={.op_code=1,.data_len=n,.payload_offset=offset,.payload_len=total,.data_ptr=s};
 ws_event_handler(NULL,0,WEBSOCKET_EVENT_DATA,&e);
}
int main(void) {
 char payload[3000];memset(payload,'x',sizeof(payload));
 frame(payload,569,0,569);assert(delivered==1 && length==569);
 frame(payload,1024,0,1500);assert(delivered==1);
 frame(payload+1024,476,1024,1500);assert(delivered==2 && length==1500);
 frame(payload,1024,0,3000);frame(payload,1024,1024,3000);frame(payload,952,2048,3000);
 assert(delivered==2); // Oversize must never reach JSON parser.
 frame(payload,2047,0,2047);assert(delivered==3 && length==2047);
 frame(payload,2048,0,2048);assert(delivered==3);
 frame(payload,100,0,569);frame(payload,469,101,569);assert(delivered==3);
 frame(payload,569,0,569);assert(delivered==4); // Recovers after rejected frames.
 esp_ip4_addr_t ip={.addr=1};dns_ok=false;
 assert(!rediscover_monitor(&ip) && ip.addr==1 && stopped==0);
 dns_ok=true;assert(rediscover_monitor(&ip));
 assert(ip.addr==42 && stopped==1 && started==1 && !strcmp(uri,"ws://42/ws"));
 order=0;stop_result=ESP_FAIL; // Already stopped by the worker.
 assert(rediscover_monitor(&ip) && started==2);
 order=0;start_result=ESP_FAIL;
 assert(!rediscover_monitor(&ip) && !s_ws_started);
 start_result=0;assert(rediscover_monitor(&ip) && s_ws_started && stopped==3);
 puts("PASS receive bounds/chunks, oversized rejection, mDNS failure/address update, stop/start recovery");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    (p/'test.c').write_text(shim+callback+recover+test)
    subprocess.run(['cc','-fsanitize=address,undefined','-g',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
