"""ASan/UBSan checks of real request adapter, HTTP/2 bridge and authentication.

Pass the upstream single-file miniz v1.14 source as the first argument. It uses
the same tinfl API as ESP32 ROM. No device or credentials are used.
"""
import ast
import gzip
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
reference = Path(sys.argv[1]).resolve()
assert reference.is_file(), 'Pass the upstream miniz v1.14 C source'
# Reuse the established real CommonCrypto PBKDF2 and NVS test fixture.
tree = ast.parse((root/'tools/test_dashboard_auth.py').read_text())
preamble = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == 'preamble' for t in n.targets))
crypto = 'static int64_t now;' + preamble.split('static int64_t now;', 1)[1].split('static int httpd_req_to_sockfd', 1)[0]
peer = 'static int fake_getpeername' + preamble.split('static int fake_getpeername', 1)[1].split('static int httpd_req_get_hdr_value_str', 1)[0]
auth = re.sub(r'^#include .*$', '', (root/'main/dashboard_auth.c').read_text(), flags=re.M).replace('getpeername(', 'fake_getpeername(')
api = (root/'main/rest_api.c').read_text()
application = api[api.index('static bool auth_required('):api.index('#if 0')]
application += api[api.index('static esp_err_t auth_status_handler('):api.index('// Text assets are stored')]
application += api[api.index('static esp_err_t serve_asset('):api.index('// iOS fetches')]

http = r'''#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
#include "esp_err.h"
typedef void *httpd_handle_t;
typedef int httpd_method_t;
typedef int httpd_err_code_t;
typedef void (*httpd_work_fn_t)(void *);
#define HTTP_GET 0
#define HTTP_POST 1
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_401_UNAUTHORIZED 401
#define HTTPD_403_FORBIDDEN 403
#define HTTPD_404_NOT_FOUND 404
#define HTTPD_408_REQ_TIMEOUT 408
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define HTTPD_RESP_USE_STRLEN -1
typedef struct httpd_req {
 httpd_method_t method;const char *uri;size_t content_len;void *user_ctx;
 int fd,status;const char *cookie,*host,*origin,*input,*set_cookie;size_t received;
 char output[1024];
} httpd_req_t;
typedef struct {const char *uri;httpd_method_t method;esp_err_t(*handler)(httpd_req_t*);void *user_ctx;} httpd_uri_t;
int httpd_req_to_sockfd(httpd_req_t*);
esp_err_t httpd_req_get_hdr_value_str(httpd_req_t*,const char*,char*,size_t);
esp_err_t httpd_req_get_url_query_str(httpd_req_t*,char*,size_t);
int httpd_req_recv(httpd_req_t*,char*,size_t);
esp_err_t httpd_resp_set_hdr(httpd_req_t*,const char*,const char*);
esp_err_t httpd_resp_set_type(httpd_req_t*,const char*);
esp_err_t httpd_resp_set_status(httpd_req_t*,const char*);
esp_err_t httpd_resp_send(httpd_req_t*,const char*,ssize_t);
esp_err_t httpd_resp_send_err(httpd_req_t*,httpd_err_code_t,const char*);
esp_err_t httpd_register_uri_handler(httpd_handle_t,const httpd_uri_t*);
esp_err_t httpd_query_key_value(const char*,const char*,char*,size_t);
'''

harness = r'''
#define _DARWIN_C_SOURCE
#include <assert.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <arpa/inet.h>
#include <CommonCrypto/CommonKeyDerivation.h>
#include "web_request.h"
#include "dashboard_auth.h"
#include "cf_tunnel.h"
#include "cJSON.h"
#define NVS_READONLY 0
#define NVS_READWRITE 1
typedef int nvs_handle_t;
static void *allocations[512];
static unsigned allocation_caps[512];
static size_t allocation_sizes[512];
static unsigned allocation_count, allocation_calls, fail_at;
static size_t live_bytes, peak_bytes;
static void *psram_alloc(size_t n,unsigned caps) {
 if (++allocation_calls == fail_at) return NULL;
 void *p=malloc(n);assert(p);
 for(unsigned i=0;i<512;i++)if(!allocations[i]){allocations[i]=p;allocation_caps[i]=caps;allocation_sizes[i]=n;allocation_count++;break;}
 live_bytes+=n;if(live_bytes>peak_bytes)peak_bytes=live_bytes;return p;
}
static void psram_free(void *p){
 for(unsigned i=0;i<512;i++)if(p && allocations[i]==p){allocations[i]=NULL;allocation_count--;live_bytes-=allocation_sizes[i];break;}
 free(p);
}
static void *heap_caps_malloc(size_t n,unsigned caps){assert(caps==3||caps==6);return psram_alloc(n,caps);}
static unsigned caps_for(void*p){for(unsigned i=0;i<512;i++)if(allocations[i]==p)return allocation_caps[i];abort();}
static void *heap_caps_calloc(size_t n,size_t size,unsigned caps){void*p=heap_caps_malloc(n*size,caps);if(p)memset(p,0,n*size);return p;}
#define free psram_free
static httpd_uri_t native_routes[48];static size_t native_count;
int httpd_req_to_sockfd(httpd_req_t*r){return r->fd;}
int httpd_req_get_hdr_value_str(httpd_req_t*r,const char*k,char*out,size_t n){
 const char*p=!strcasecmp(k,"cookie")?r->cookie:!strcasecmp(k,"host")?r->host:r->origin;
 if(!p||strlen(p)>=n)return ESP_FAIL;strcpy(out,p);return ESP_OK;
}
int httpd_req_get_url_query_str(httpd_req_t*r,char*out,size_t n){const char*p=strchr(r->uri,'?');if(!p||strlen(++p)>=n)return ESP_FAIL;strcpy(out,p);return ESP_OK;}
int httpd_query_key_value(const char*q,const char*k,char*out,size_t n){
 size_t z=strlen(k);while(*q){const char*e=strchr(q,'&');size_t len=e?(size_t)(e-q):strlen(q);
 if(len>z&&!strncmp(q,k,z)&&q[z]=='='){size_t v=len-z-1;if(v>=n)return ESP_FAIL;memcpy(out,q+z+1,v);out[v]=0;return ESP_OK;}
 if(!e)break;q=e+1;}return ESP_ERR_NOT_FOUND;
}
int httpd_req_recv(httpd_req_t*r,char*out,size_t n){if(n>r->content_len-r->received)n=r->content_len-r->received;memcpy(out,r->input+r->received,n);r->received+=n;return n;}
int httpd_resp_set_hdr(httpd_req_t*r,const char*k,const char*v){if(!strcasecmp(k,"set-cookie"))r->set_cookie=v;return ESP_OK;}
int httpd_resp_set_type(httpd_req_t*r,const char*v){(void)r;(void)v;return ESP_OK;}
int httpd_resp_set_status(httpd_req_t*r,const char*v){r->status=atoi(v);return ESP_OK;}
int httpd_resp_send(httpd_req_t*r,const char*p,ssize_t n){if(n<0)n=strlen(p);assert((size_t)n<sizeof r->output);if(n)memcpy(r->output,p,n);r->output[n]=0;return ESP_OK;}
int httpd_resp_send_err(httpd_req_t*r,int status,const char*p){r->status=status;return httpd_resp_send(r,p,-1);}
int httpd_register_uri_handler(httpd_handle_t s,const httpd_uri_t*r){(void)s;native_routes[native_count++]=*r;return ESP_OK;}
bool compressed_asset_accepts_gzip(httpd_req_t*r){(void)r;return false;}
int compressed_asset_send_identity(httpd_req_t*r,const unsigned char*p,size_t n,size_t raw){(void)r;(void)p;(void)n;(void)raw;return ESP_FAIL;}

static httpd_work_fn_t work;static void *work_arg;static bool queue_fail;
esp_err_t rest_api_queue_work(httpd_work_fn_t fn,void*arg){if(queue_fail)return ESP_FAIL;assert(!work);work=fn;work_arg=arg;return ESP_OK;}
static void run_worker(void){assert(work);httpd_work_fn_t fn=work;void*arg=work_arg;work=NULL;work_arg=NULL;fn(arg);}

struct cft_stream {
 cft_stream_handlers_t handlers;void*ctx;bool complete,ended,closed,fail_headers,fail_write;
 int status;char cookie[256],type[80],cache[100],etag[100];
 char output[100000];size_t size,buffered,max_buffered;
};
void cft_stream_set_handlers(cft_stream_t*s,const cft_stream_handlers_t*h,void*ctx){s->handlers=*h;s->ctx=ctx;}
bool cft_stream_body_ended(const cft_stream_t*s){return s->complete;}
size_t cft_stream_buffered(const cft_stream_t*s){return s->buffered;}
static void close_stream(cft_stream_t*s){assert(!s->closed);s->closed=true;if(s->handlers.on_close)s->handlers.on_close(s,s->ctx,s->ended);s->ctx=NULL;}
int cft_stream_send_headers(cft_stream_t*s,int status,const cft_header_t*h,size_t n){
 if(s->fail_headers)return -1;s->status=status;
 for(size_t i=0;i<n;i++){
  char*out=!strcasecmp(h[i].name,"set-cookie")?s->cookie:!strcasecmp(h[i].name,"content-type")?s->type:!strcasecmp(h[i].name,"cache-control")?s->cache:!strcasecmp(h[i].name,"etag")?s->etag:NULL;
  if(out)strcpy(out,h[i].value);
 }return 0;
}
int cft_stream_write(cft_stream_t*s,const void*p,size_t n){
 if(s->fail_write)return -1;assert(n<=512&&s->buffered==0&&s->size+n<=sizeof s->output);
 memcpy(s->output+s->size,p,n);s->size+=n;s->buffered+=n;if(s->buffered>s->max_buffered)s->max_buffered=s->buffered;return 0;
}
int cft_stream_end(cft_stream_t*s){s->ended=true;return 0;}
void cft_stream_reset(cft_stream_t*s){close_stream(s);}
int cft_stream_respond(cft_stream_t*s,int status,const char*type,const void*p,size_t n){s->status=status;if(type)strcpy(s->type,type);if(n)memcpy(s->output,p,n);s->size=n;s->ended=true;return 0;}

#include "crypto_fixture.inc"
#include "peer_fixture.inc"
#include "web_request.c"
#include "auth_actual.inc"
#include "auth_handlers.inc"
#include "cloudflare_http.c"
#include "payload.inc"
static const char etag[]="\"123456789012345678901234\"";
static esp_err_t asset(web_request_t*r){return serve_asset(r,"application/javascript",NULL,sizeof plaintext,etag,packed,sizeof packed,"\"gzip-etag\"");}
static esp_err_t public_asset(web_request_t*r){return serve_asset(r,"image/png",NULL,sizeof plaintext,etag,packed,sizeof packed,"\"gzip-etag\"");}
static unsigned mutation_count;
static esp_err_t mutate(web_request_t*r){mutation_count++;char*owned=buffer_memory_alloc(8);assert(owned);memcpy(owned,"changed",8);return web_send_owned(r,owned);}
static esp_err_t reflect(web_request_t*r){char b[8192];size_t n=0;while(n<r->content_len){int got=web_recv(r,b+n,r->content_len-n);if(got<=0)return ESP_FAIL;n+=got;}return web_send(r,b,n);}
static const web_route_t asset_route={"/dashboard.js",HTTP_GET,asset};
static const web_route_t public_route={"/test.png",HTTP_GET,public_asset};
static const web_route_t mutate_route={"/mutate",HTTP_POST,mutate};
static const web_route_t reflect_route={"/reflect",HTTP_POST,reflect};

static void request(cft_stream_t*s,const char*method,const char*path,const cft_header_t*h,size_t n,const char*input){
 cft_request_t req={.method=method,.path=path,.authority="monitor.example",.scheme="https",.headers=h,.num_headers=n,.content_length=input?(int64_t)strlen(input):0};
 s->complete=!input;cloudflare_http_request(s,&req,100);
 if(s->ctx){direct_request_t*r=s->ctx;assert(caps_for(r)==3&&caps_for(r->storage)==3&&caps_for(r->control)==6);}
 if(input&&s->ctx){size_t len=strlen(input),half=len/2;s->handlers.on_body(s,s->ctx,(const uint8_t*)input,half);s->handlers.on_body(s,s->ctx,(const uint8_t*)input+half,len-half);s->complete=true;s->handlers.on_body_end(s,s->ctx);}
}
static void finish(cft_stream_t*s){
 assert(cloudflare_http_wait_ms(NULL)==5);cloudflare_http_poll(101);if(work)run_worker();cloudflare_http_poll(102);
 for(unsigned i=0;!s->ended&&!s->closed&&i<1000;i++){s->buffered=0;s->handlers.on_writable(s,s->ctx);}
 assert(s->ended||s->closed);if(!s->closed)close_stream(s);
}
static void clean(void){assert(cloudflare_http_wait_ms(NULL)==0);assert(allocation_count==0&&live_bytes==0&&!atomic_load(&http_busy)&&!work);for(size_t i=0;i<DIRECT_REQUESTS;i++)assert(!pending[i]);}

int main(void){
 dashboard_auth_init();assert(dashboard_auth_set_password(NULL,"test-password")==ESP_OK);
 const web_route_t*reg[]={&auth_status_uri,&auth_login_uri,&auth_setup_uri,&auth_password_uri,&auth_logout_uri,&asset_route,&public_route,&mutate_route,&reflect_route};
 for(size_t i=0;i<sizeof reg/sizeof reg[0];i++)assert(web_register_handler((void*)1,reg[i])==ESP_OK);
 // LAN still reaches the same application handler through a real native wrapper.
 httpd_req_t lan={.fd=2,.uri="/api/auth/status",.method=HTTP_GET,.user_ctx=native_routes[0].user_ctx};
 assert(native_routes[0].handler(&lan)==ESP_OK&&strstr(lan.output,"true"));
 cft_stream_t s={0};request(&s,"GET","/api/auth/status",NULL,0,NULL);finish(&s);assert(s.status==200);clean();
 s=(cft_stream_t){0};request(&s,"GET","/dashboard.js",NULL,0,NULL);finish(&s);assert(s.status==401);clean();
 cft_header_t origin[]={ {"origin","https://monitor.example"} };
 s=(cft_stream_t){0};request(&s,"POST","/api/auth/login",origin,1,"{\"password\":\"test-password\",\"remember\":true}");finish(&s);
 assert(s.status==200&&strstr(s.cookie,"Secure")&&strstr(s.cookie,"Max-Age="));
 char cookie[100];size_t cn=strcspn(s.cookie,";");memcpy(cookie,s.cookie,cn);cookie[cn]=0;clean();
 cft_header_t authorized[]={ {"cookie",cookie},{"accept-encoding","gzip"} };
 s=(cft_stream_t){0};request(&s,"GET","/dashboard.js?v=123456789012345678901234",authorized,2,NULL);finish(&s);
 assert(s.status==200&&strstr(s.cache,"immutable")&&s.size==sizeof packed&&!memcmp(s.output,packed,sizeof packed));clean();
 // Identity fallback spans multiple 32KiB dictionary blocks, with 512B sends.
 authorized[1].value="identity";s=(cft_stream_t){0};request(&s,"GET","/dashboard.js",authorized,2,NULL);finish(&s);
 assert(s.size==sizeof plaintext&&!memcmp(s.output,plaintext,sizeof plaintext)&&s.max_buffered<=512);clean();
 authorized[1].value="gzip;q=0";s=(cft_stream_t){0};request(&s,"GET","/dashboard.js",authorized,2,NULL);finish(&s);assert(s.size==sizeof plaintext);clean();
 cft_header_t conditional[]={ {"cookie",cookie},{"if-none-match",etag} };
 s=(cft_stream_t){0};request(&s,"GET","/dashboard.js",conditional,2,NULL);finish(&s);assert(s.status==304&&s.size==0);clean();
 s=(cft_stream_t){0};request(&s,"GET","/dashboard.js?v=stale",authorized,2,NULL);finish(&s);assert(s.status==404);clean();
 cft_header_t bad_origin[]={ {"cookie",cookie},{"origin","https://evil.example"} };
 s=(cft_stream_t){0};request(&s,"POST","/api/auth/logout",bad_origin,2,"{}");finish(&s);assert(s.status==403);clean();
 dashboard_auth_init();s=(cft_stream_t){0};request(&s,"POST","/api/auth/setup",origin,1,"{\"password\":\"test-password\",\"confirm_password\":\"test-password\"}");finish(&s);assert(s.status==403);clean();
 // Request-owned headers survive caller buffers disappearing; split Cookie joins.
 char first[]="part=1",second[]="other=2";cft_header_t split[]={ {"cookie",first},{"cookie",second} };
 s=(cft_stream_t){0};request(&s,"POST","/reflect",split,2,"fragmented input");memset(first,0,sizeof first);memset(second,0,sizeof second);char combined[80];assert(web_header(&((direct_request_t*)s.ctx)->request,"Cookie",combined,sizeof combined)==ESP_OK&&!strcmp(combined,"part=1; other=2"));finish(&s);assert(s.size==16&&!memcmp(s.output,"fragmented input",16));clean();
 cft_header_t duplicate_origin[]={ {"origin","a"},{"origin","b"} };
 s=(cft_stream_t){0};request(&s,"GET","/test.png",duplicate_origin,2,NULL);assert(s.status==400&&!s.ctx);clean();
 // Duplicate large headers cannot wrap the bounded capture calculation.
 char large[4097];memset(large,'a',4096);large[4096]=0;cft_header_t oversized[]={{"cookie","a"},{"cookie",large}};
 s=(cft_stream_t){0};request(&s,"GET","/test.png",oversized,2,NULL);assert(s.status==431&&!s.ctx);clean();
 // A peer ending before the declared body length never reaches the worker.
 cft_request_t partial={.method="POST",.path="/mutate",.authority="monitor.example",.content_length=5};
 s=(cft_stream_t){0};cloudflare_http_request(&s,&partial,100);s.handlers.on_body(&s,s.ctx,(const uint8_t*)"{}",2);s.handlers.on_body_end(&s,s.ctx);assert(s.status==400);close_stream(&s);clean();
 // Cancellation before dispatch never mutates; after dispatch retains worker ref.
 s=(cft_stream_t){0};request(&s,"POST","/mutate",NULL,0,"{}");close_stream(&s);cloudflare_http_poll(101);assert(!mutation_count);clean();
 s=(cft_stream_t){0};request(&s,"POST","/mutate",NULL,0,"{}");cloudflare_http_poll(101);assert(work);close_stream(&s);run_worker();assert(!mutation_count);clean();
 s=(cft_stream_t){0};request(&s,"POST","/mutate",NULL,0,"{}");cloudflare_http_poll(101);run_worker();close_stream(&s);assert(mutation_count==1);clean();
 // A new connection can queue while a cancelled old worker is still pending.
 cft_stream_t next={0};s=(cft_stream_t){0};request(&s,"POST","/mutate",NULL,0,"{}");cloudflare_http_poll(101);close_stream(&s);
 request(&next,"GET","/test.png",NULL,0,NULL);run_worker();finish(&next);assert(mutation_count==1);clean();
 // Timeouts and a full queue are bounded and do not leak captured requests.
 cft_stream_t*many=calloc(DIRECT_REQUESTS+1,sizeof *many);
 for(size_t i=0;i<DIRECT_REQUESTS+1;i++)request(&many[i],"GET","/test.png",NULL,0,NULL);
 assert(many[DIRECT_REQUESTS].status==503);
 cloudflare_http_poll(100+DIRECT_TIMEOUT_US);
 for(size_t i=0;i<DIRECT_REQUESTS;i++){assert(many[i].status==503);close_stream(&many[i]);}free(many);clean();
 queue_fail=true;s=(cft_stream_t){0};request(&s,"GET","/test.png",NULL,0,NULL);cloudflare_http_poll(101);assert(!work&&!atomic_load(&http_busy));queue_fail=false;finish(&s);clean();
 // Every allocation failure in capture, response headers and identity decoding
 // must close cleanly, including reset callbacks firing synchronously.
 for(unsigned step=1;step<24;step++){
  allocation_calls=0;fail_at=step;s=(cft_stream_t){0};request(&s,"GET","/test.png",NULL,0,NULL);
  if(s.ctx)finish(&s);fail_at=0;clean();
 }
 for(unsigned mode=0;mode<2;mode++){
  s=(cft_stream_t){.fail_headers=mode==0,.fail_write=mode==1};request(&s,"GET","/test.png",NULL,0,NULL);finish(&s);assert(s.closed);clean();
 }
 puts("PASS actual HTTP2 adapter/worker/auth, native handler, cookies/CSRF, asset versions/304, gzip/identity, 512B flow control, cancellation, bounded queue, timeouts and allocation failure");
}
'''

with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    (p/'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n#define ESP_ERR_INVALID_ARG 1\n#define ESP_ERR_NOT_FOUND 2\n#define ESP_ERR_TIMEOUT 3\n#define ESP_ERR_NO_MEM 4\n#define ESP_ERR_INVALID_STATE 5\n#define ESP_ERR_HTTPD_RESULT_TRUNC 6\n')
    (p/'esp_http_server.h').write_text(http)
    (p/'sdkconfig.h').write_text('#pragma once\n#define CONFIG_SPIRAM 1\n')
    (p/'esp_log.h').write_text('#pragma once\n#define ESP_LOGE(...) ((void)0)\n')
    (p/'esp_heap_caps.h').write_text('#pragma once\n#define MALLOC_CAP_SPIRAM 1\n#define MALLOC_CAP_8BIT 2\n#define MALLOC_CAP_INTERNAL 4\n')
    (p/'miniz.h').write_text('#define MINIZ_HEADER_FILE_ONLY\n#include "'+str(reference)+'"\n')
    (p/'crypto_fixture.inc').write_text(crypto)
    (p/'peer_fixture.inc').write_text(peer)
    (p/'auth_actual.inc').write_text(auth)
    (p/'auth_handlers.inc').write_text(application)
    raw = bytes((i*i + 17*i) % 251 for i in range(70000))
    packed = gzip.compress(raw, compresslevel=9, mtime=0)
    (p/'payload.inc').write_text('static const unsigned char plaintext[]={'+','.join(map(str,raw))+'};\nstatic const unsigned char packed[]={'+','.join(map(str,packed))+'};\n')
    (p/'test.c').write_text(harness)
    cjson = root/'managed_components/espressif__cjson/cJSON'
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-deprecated-declarations',
                    '-fsanitize=address,undefined','-fsanitize-address-use-after-return=always','-I'+str(p),'-I'+str(root/'main'),
                    '-I'+str(root/'components/esp_cf_tunnel/include'),'-I'+str(root.parent/'components/captive_portal/include'),
                    '-I'+str(cjson),str(p/'test.c'),str(cjson/'cJSON.c'),str(reference),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,timeout=30)
