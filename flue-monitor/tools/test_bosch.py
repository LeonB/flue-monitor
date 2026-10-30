"""Execute firmware protocol, credential lifecycle, polling and HTTP guards under sanitizers.

Real cJSON and production C functions; network, NVS and RTOS are deterministic shims.
Does not contact Bosch, use real tokens or write device settings.
"""
from pathlib import Path
import subprocess
import tempfile
import base64
import hashlib
from urllib.parse import urlparse, parse_qs

root = Path(__file__).resolve().parents[1]
src = (root / 'main/bosch_client.c').read_text()
core = src[src.index('#define CLIENT_ID'):src.index('static void task(')]
start = core.index('static cJSON *request(')
end = core.index('// One NVS value', start)
core = core[:start] + '''static cJSON *request(const char *url,const char *body,bool authorized) {
 request_count++; http_status=mock_http_status;
 if(body) { assert(!authorized); assert(!strcmp(url,TOKEN_URL)); snprintf(last_form,sizeof last_form,"%s",body); }
 else { assert(authorized); assert(access_token); assert(!strncmp(url,API_ROOT,strlen(API_ROOT))); }
 return mock_response ? cJSON_Parse(mock_response) : NULL;
}
''' + core[end:]
handler = src[src.index('static esp_err_t unavailable('):src.index('void bosch_client_start(')]
preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bosch_protocol.h"
#include "cJSON.h"
#include <CommonCrypto/CommonDigest.h>
#define PSA_ALG_SHA_256 1
#define PSA_SUCCESS 0
static int psa_hash_compute(int alg,const uint8_t *data,size_t len,uint8_t *out,size_t cap,size_t *n){assert(alg==1 && cap>=32);CC_SHA256(data,(CC_LONG)len,out);*n=32;return 0;}
static int mbedtls_base64_encode(unsigned char *out,size_t cap,size_t *n,const unsigned char *in,size_t len){
 static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 assert(cap>=4*((len+2)/3)+1);size_t j=0;
 for(size_t i=0;i<len;i+=3){unsigned x=(unsigned)in[i]<<16;if(i+1<len)x|=in[i+1]<<8;if(i+2<len)x|=in[i+2];out[j++]=alphabet[x>>18];out[j++]=alphabet[(x>>12)&63];out[j++]=i+1<len?alphabet[(x>>6)&63]:'=';out[j++]=i+2<len?alphabet[x&63]:'=';}
 out[j]=0;*n=j;return 0;
}
typedef int SemaphoreHandle_t; typedef int QueueHandle_t; typedef int TaskHandle_t;
typedef int esp_err_t; typedef int nvs_handle_t;
#define portMAX_DELAY 0
#define pdTRUE 1
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NVS_NOT_FOUND 2
#define NVS_READWRITE 1
#define NVS_READONLY 0
#define HTTP_EVENT_ON_DATA 1
#define HTTP_GET 0
#define HTTP_POST 1
#define HTTPD_401_UNAUTHORIZED 401
#define HTTPD_403_FORBIDDEN 403
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_408_REQ_TIMEOUT 408
static int64_t clock_s=100;
static int64_t esp_timer_get_time(void){return clock_s*1000000;}
static void xSemaphoreTake(int a,int b){} static void xSemaphoreGive(int a){}
static void *buffer_memory_alloc(size_t n){return malloc(n);}
static void *buffer_memory_calloc(size_t n,size_t s){return calloc(n,s);}
static void esp_fill_random(void *p,size_t n){memset(p,42,n);}
static int mock_http_status=200, request_count;
static const char *mock_response;
static char last_form[20000];
static bool storage_fails;
static char *stored;
static esp_err_t nvs_open(const char *s,int mode,int *h){assert(!strcmp(s,"bosch")); *h=1;return 0;}
static void nvs_close(int h){}
static esp_err_t nvs_commit(int h){return storage_fails ? -1 : 0;}
static esp_err_t nvs_set_str(int h,const char *key,const char *s){if(storage_fails)return -1;free(stored);stored=strdup(s);return 0;}
static esp_err_t nvs_erase_key(int h,const char *key){if(storage_fails)return -1;free(stored);stored=NULL;return 0;}
static esp_err_t nvs_get_str(int h,const char *key,char *p,size_t *n){if(!stored)return 2;if(p){assert(*n>=strlen(stored)+1);strcpy(p,stored);}*n=strlen(stored)+1;return 0;}
typedef struct {int event_id;void *user_data;int data_len;void *data;} esp_http_client_event_t;
typedef struct {int method;int content_len;const char *body;} httpd_req_t;
static bool authorized, csrf; static int response_code; static char response[5000]; static char *queued;
static bool dashboard_auth_check(httpd_req_t *r){return authorized;}
static bool dashboard_auth_check_csrf(httpd_req_t *r){return csrf;}
static int httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v){return 0;}
static int httpd_resp_set_type(httpd_req_t *r,const char *v){return 0;}
static int httpd_resp_set_status(httpd_req_t *r,const char *s){response_code=atoi(s);return 0;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){snprintf(response,sizeof response,"%s",s);return 0;}
static int httpd_resp_send_err(httpd_req_t *r,int c,const char *s){response_code=c;return httpd_resp_sendstr(r,s);}
static int httpd_req_recv(httpd_req_t *r,char *buf,size_t n){if(!r->body)return -1;memcpy(buf,r->body,n);return n;}
static int xQueueSend(int q,char **s,int wait){queued=*s;return 1;}
'''
tests = r'''
static void cmd(const char *json){cJSON *o=cJSON_Parse(json);command(o);cJSON_Delete(o);}
static bool tokens(const char *json){cJSON *o=cJSON_Parse(json);bool ok=accept_tokens(o);cJSON_Delete(o);return ok;}
int main(void) {
 assert(begin_login());assert(auth_deadline==clock_s+1200);assert(strlen(verifier)==64);assert(strlen(oauth_state)==64);
 printf("AUTH_URL %s\n",status.auth_url);clear_login();
 char code[1024];
 assert(bosch_callback(BOSCH_REDIRECT "?code=a%2Bb%2Fc&state=expected","expected",code,sizeof code));assert(!strcmp(code,"a+b/c"));
 const char *invalid[]={BOSCH_REDIRECT "?code=a&state=wrong",BOSCH_REDIRECT "?code=a&state=expected&code=b",
 BOSCH_REDIRECT "?code=a&state=expected&state=expected",BOSCH_REDIRECT "?code=a%00b&state=expected",
 BOSCH_REDIRECT "?code=%&state=expected",BOSCH_REDIRECT "?code=a&state=expected#x",BOSCH_REDIRECT "?code=a",
 "https://singlekey-id.com/auth/connect/authorize/callback?response_type=code",BOSCH_REDIRECT "?code=a&state=expected&error=denied"};
 for(size_t i=0;i<sizeof invalid/sizeof *invalid;i++)assert(!bosch_callback(invalid[i],"expected",code,sizeof code));
 assert(!bosch_callback(BOSCH_REDIRECT "?code=abcd&state=expected","expected",code,4));
 assert(bosch_id_valid("101033665") && !bosch_id_valid("abc/../../x") && !bosch_id_valid("a?x"));
 assert(bosch_zone_valid("zn1") && !bosch_zone_valid("zn1/x") && !bosch_zone_valid("zn"));
 assert(bosch_temperature_valid(19.6) && !bosch_temperature_valid(1000) && !bosch_temperature_valid(INFINITY) && !bosch_temperature_valid(NAN));
 char *e=encode("a+b/c?=& ");assert(!strcmp(e,"a%2Bb%2Fc%3F%3D%26%20"));free(e);
 puts("PASS callback origin/state, duplicates, encoding, bounds, resource paths and 1000°C sentinel rejection");
 // An oversized/chunked network response cannot overwrite its buffer.
 response_t r={.data=calloc(RESPONSE_MAX,1),.size=RESPONSE_MAX-2};
 esp_http_client_event_t ev={.event_id=HTTP_EVENT_ON_DATA,.user_data=&r,.data_len=3,.data="abc"};
 assert(http_event(&ev)==ESP_FAIL && r.overflow);free(r.data);
 assert(tokens("{\"access_token\":\"old-access\",\"refresh_token\":\"old-refresh\",\"expires_in\":3600}"));
 assert(!tokens("{\"access_token\":\"bad\",\"expires_in\":null}"));assert(!strcmp(access_token,"old-access"));
 mock_response="{\"access_token\":\"new-access\",\"refresh_token\":\"rotated-refresh\",\"expires_in\":3600}";
 assert(refresh());assert(strstr(last_form,"grant_type=refresh_token"));assert(strstr(stored,"rotated-refresh"));assert(status.refreshes==1);
 wipe_free(access_token);access_token=NULL;wipe_free(refresh_token);refresh_token=NULL;load_credentials();
 assert(!strcmp(refresh_token,"rotated-refresh") && !access_token);
 assert(tokens("{\"access_token\":\"after-reboot\",\"expires_in\":3600}"));assert(!strcmp(refresh_token,"rotated-refresh"));
 mock_response=NULL;mock_http_status=401;assert(!discover() && expiry==0);mock_http_status=200;expiry=clock_s+3600;
 strcpy(device,"101033665");
 mock_response="{\"references\":[{\"id\":\"/zones/zn1\"},{\"id\":\"/zones/zn2\"},{\"id\":\"/zones/zn2\"},{\"id\":\"https://evil.invalid\"},{\"id\":\"/zones/zn1/extra\"}]}";
 discover_zones();assert(status.zone_count==2 && !strcmp(status.zones[1],"zn2"));
 int zone_calls=request_count;discover_zones();assert(request_count==zone_calls);
 clock_s+=601;mock_response=NULL;discover_zones();assert(status.zone_count==2);
 mock_response="{\"value\":19.6}";assert(poll_temperature());assert(status.available && status.temperature==19.6);
 double room=-999;lock=1;assert(bosch_client_get_temperature(&room) && room==19.6);
 clock_s+=181;room=-999;assert(!bosch_client_get_temperature(&room) && room==-999);clock_s-=181;
 assert(!bosch_client_get_temperature(NULL));
 mock_response="{\"value\":1000}";assert(!poll_temperature());assert(!status.available && !strcmp(status.state,"invalid_reading"));assert(!bosch_client_get_temperature(&room));
 mock_response="{\"value\":null}";assert(!poll_temperature());
 mock_response=NULL;mock_http_status=401;assert(!poll_temperature());assert(!access_token && expiry==0);
 mock_http_status=503;assert(!refresh() && !reauth);
 mock_http_status=400;assert(!refresh() && reauth);
 puts("PASS token rotation and restart restoration, refreshed-token reading, invalid values, 401 and transient/permanent failures");
 int before=request_count;strcpy(oauth_state,"expected");auth_deadline=clock_s+1200;
 cmd("{\"action\":\"callback\",\"callback\":\"com.bosch.tt.dashtt.pointt://app/login?code=a&state=wrong\"}");assert(request_count==before);
 auth_deadline=clock_s;cmd("{\"action\":\"callback\",\"callback\":\"com.bosch.tt.dashtt.pointt://app/login?code=a&state=expected\"}");assert(request_count==before);
 storage_fails=true;cmd("{\"action\":\"select\",\"device\":\"222\",\"zone\":\"zn2\"}");assert(!strcmp(device,"101033665") && !strcmp(zone,"zn1"));
 cmd("{\"action\":\"disconnect\"}");assert(refresh_token);storage_fails=false;
 worker=1;httpd_req_t req={.method=HTTP_GET};authorized=false;handler(&req);assert(response_code==401);
 authorized=true;handler(&req);assert(!strstr(response,"rotated-refresh") && !strstr(response,"after-reboot"));
 req.method=HTTP_POST;csrf=false;handler(&req);assert(response_code==403 && !queued);
 csrf=true;req.content_len=2048;handler(&req);assert(response_code==400);
 req.body="{\"action\":\"start\"}";req.content_len=strlen(req.body);handler(&req);assert(response_code==202 && queued);
 free(queued);queued=NULL;handler(&req);assert(response_code==409 && !queued);
 req.method=HTTP_GET;status.available=true;status.sampled=clock_s-181;handler(&req);assert(strstr(response,"\"available\":false") && strstr(response,"\"temperature_c\":null"));
 cmd("{\"action\":\"disconnect\"}");assert(!stored && !access_token && !refresh_token && !status.linked);
 puts("PASS expired/replayed login guard, storage failure, authenticated/CSRF-protected API, single queued job, stale data and disconnect");
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='flue-bosch-test-') as tmp:
    p=Path(tmp);(p/'test.c').write_text(preamble+core+handler+tests)
    cjson=root/'managed_components/espressif__cjson/cJSON'
    subprocess.run(['clang','-std=c11','-D_DARWIN_C_SOURCE','-g','-Wno-deprecated-declarations','-fsanitize=address,undefined',
                    '-I'+str(root/'main'),'-I'+str(cjson),str(p/'test.c'),str(cjson/'cJSON.c'),'-o',str(p/'test')],check=True)
    result = subprocess.run([str(p/'test')],check=True,capture_output=True,text=True)
    for line in result.stdout.splitlines():
        if line.startswith('AUTH_URL '):
            outer = parse_qs(urlparse(line[9:]).query)
            inner = parse_qs(urlparse(outer['ReturnUrl'][0]).query)
            assert inner['redirect_uri'] == ['com.bosch.tt.dashtt.pointt://app/login']
            verifier = '2a' * 32  # deterministic esp_fill_random shim
            expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            assert inner['code_challenge'] == [expected]
            assert inner['state'] == [verifier] and inner['code_challenge_method'] == ['S256']
            print('PASS actual authorization URL nesting, callback, state and PKCE challenge against independent SHA256')
        else:
            print(line)
