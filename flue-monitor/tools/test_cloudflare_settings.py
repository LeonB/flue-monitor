"""Exercise actual NVS migration, validation and REST settings code on the host.

Requires an existing ESP-IDF build (uses its cJSON dependency).
"""
import json
from pathlib import Path
from web_test_shim import native_source
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
idf = Path(json.loads((root / 'build/project_description.json').read_text())['idf_path'])
cjson = root / 'managed_components/espressif__cjson/cJSON'
if not cjson.exists():
    cjson = idf / 'components/json/cJSON'
header = (root / 'main/settings.h').read_text().replace('#pragma once', '').replace('#include "esp_err.h"', '')
config = (root / 'main/config.h').read_text().replace('#pragma once', '')
settings = re.sub(r'^#include .*$','', (root / 'main/settings.c').read_text(), flags=re.M)
api = native_source((root / 'main/rest_api.c').read_text(), tunnel='req->user_ctx')
serialization = api[api.index('static void settings_to_json('):api.index('static const httpd_uri_t settings_get_uri')]
post = api[api.index('static esp_err_t settings_post_handler('):api.index('static const httpd_uri_t settings_post_uri')]
preamble = r'''
#define _DARWIN_C_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define FLUE_TRACE(...) ((void)0)
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <math.h>
#include <ctype.h>
#include "cJSON.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 1
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define portMAX_DELAY 0
#define NVS_READONLY 0
#define NVS_READWRITE 1
typedef int nvs_handle_t;
typedef int SemaphoreHandle_t;
static unsigned char stored[16384];
static size_t stored_len;
static unsigned char stored_v2[16384];static size_t stored_v2_len;
static unsigned char stored_v3[16384];static size_t stored_v3_len;
static unsigned writes, wakes;
static bool fail_body_alloc;
static int alloc_calls, fail_alloc_at;
static void *buffer_memory_calloc(size_t n,size_t size) {alloc_calls++;return fail_body_alloc || alloc_calls==fail_alloc_at ? NULL : calloc(n,size);}
static int xSemaphoreCreateMutex(void) {return 1;}
static void xSemaphoreTake(int a,int b) {(void)a;(void)b;}
static void xSemaphoreGive(int a) {(void)a;}
static int nvs_open(const char *a,int b,int *c) {(void)a;(void)b;*c=1;return ESP_OK;}
static int nvs_get_blob(int a,const char *key,void *out,size_t *n) {
 (void)a;unsigned char *data=!strcmp(key,"settings_v3")?stored_v3:!strcmp(key,"settings_v2")?stored_v2:stored;
 size_t len=!strcmp(key,"settings_v3")?stored_v3_len:!strcmp(key,"settings_v2")?stored_v2_len:stored_len;
 if(!len)return ESP_FAIL;if(!out){*n=len;return ESP_OK;}if(*n<len)return ESP_FAIL;memcpy(out,data,len);*n=len;return ESP_OK;
}
static int nvs_set_blob(int a,const char *key,const void *out,size_t n) {
 (void)a;assert(!strcmp(key,"settings_v3")&&n<=sizeof stored_v3);memcpy(stored_v3,out,n);stored_v3_len=n;writes++;return ESP_OK;
}
static int nvs_commit(int a) {(void)a;return ESP_OK;}
static void nvs_close(int a) {(void)a;}
typedef struct {size_t content_len;void *user_ctx;const char *input;int received,status;char response[4096];} httpd_req_t;
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_403_FORBIDDEN 403
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define HTTPD_SOCK_ERR_TIMEOUT -2
static int httpd_req_recv(httpd_req_t *r,char *out,int n) {memcpy(out,r->input+r->received,n);r->received+=n;return n;}
static int httpd_resp_send_err(httpd_req_t *r,int status,const char *message) {r->status=status;snprintf(r->response,sizeof r->response,"%s",message);return ESP_OK;}
static int httpd_resp_set_type(httpd_req_t *r,const char *type) {(void)r;(void)type;return ESP_OK;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *message) {r->status=200;snprintf(r->response,sizeof r->response,"%s",message);return ESP_OK;}
static bool configured=true, authenticated=true;
static bool dashboard_auth_is_configured(void) {return configured;}
static bool dashboard_auth_is_remote(httpd_req_t *r) {return r->user_ctx != NULL;}
static bool dashboard_auth_check(httpd_req_t *r) {(void)r;return authenticated;}
static bool auth_required(httpd_req_t *r) {if(authenticated)return false;r->status=401;return true;}
static bool dashboard_auth_check_csrf(httpd_req_t *r) {(void)r;return true;}
static double round_to(double a,double b) {return round(a/b)*b;}
static uint32_t ws_server_settings_revision(bool advance) {static uint32_t revision=1;if(advance)revision++;return revision;}
static void ws_server_broadcast_settings_changed(void) {}
static void cloudflare_tunnel_start(void) {wakes++;}
static const char *esp_err_to_name(int error) {(void)error;return "error";}
'''
tests = r'''
static void write_api(cJSON *body,bool remote,int status) {
 char *text=cJSON_PrintUnformatted(body);assert(text);
 httpd_req_t request={.content_len=(int)strlen(text),.user_ctx=remote?(void *)1:NULL,.input=text};
 settings_post_handler(&request);assert(request.status==status);free(text);
}
int main(void) {
 (void)TAG;(void)esp_err_to_name;
 settings_t legacy;set_defaults(&legacy);legacy.log_heartbeat_min=87;
 strcpy(legacy.google_sheets_secret,"preserve-sheets");strcpy(legacy.zone_cold_color,"#fab100");
 const size_t prefix=260,old_cf=776,old_size=5008;
 assert(offsetof(settings_t,cloudflare)==prefix&&sizeof(settings_t)==4492);
 const size_t sizes[]={old_cf,old_cf+16,old_cf+20,prefix,prefix+388,
   offsetof(settings_t,zone_cold_color),offsetof(settings_t,breathing_exponent),offsetof(settings_t,maximum_brightness)};
 for(unsigned key=0;key<2;key++)for(size_t i=0;i<sizeof sizes/sizeof sizes[0];i++) {
   stored_v3_len=stored_v2_len=stored_len=0;
   unsigned char*dest=key?stored_v2:stored;size_t*len=key?&stored_v2_len:&stored_len;
   memset(dest,0,16384);memcpy(dest,&legacy,sizes[i]<prefix?sizes[i]:prefix);*len=sizes[i];
   settings_init();settings_t migrated;settings_get(&migrated);
   assert(migrated.log_heartbeat_min==87&&!strcmp(migrated.google_sheets_secret,"preserve-sheets"));
   if(sizes[i]>=offsetof(settings_t,breathing_exponent))assert(!strcmp(migrated.zone_cold_color,"#fab100"));
   assert(!migrated.cloudflare.enabled&&migrated.cloudflare.connections==1&&!*migrated.cloudflare.token);
 }
 // Exact deployed v2 layout: the removed 516-byte block is never copied.
 settings_t c=legacy;c.cloudflare.enabled=1;c.cloudflare.connections=4;
 strcpy(c.cloudflare.hostname,"cf-test.example.nl");strcpy(c.cloudflare.token,"eyJ0ZXN0IjoiZHVtbXkifQ==");
 memset(stored_v2,0,sizeof stored_v2);memcpy(stored_v2,&c,prefix);
 memset(stored_v2+prefix,0xa5,516);memcpy(stored_v2+old_cf,&c.cloudflare,sizeof c.cloudflare);
 stored_v2_len=old_size;stored_v3_len=0;settings_init();settings_t restored;settings_get(&restored);
 assert(!memcmp(&c,&restored,sizeof c));
 unsigned char previous[5008];memcpy(previous,stored_v2,old_size);
 assert(settings_set(&c)==ESP_OK&&stored_v3_len==sizeof c&&!memcmp(previous,stored_v2,old_size));
 settings_init();settings_get(&restored);assert(!memcmp(&c,&restored,sizeof c));
 // Unsupported/truncated v3 must not silently resurrect an older valid v2.
 stored_v3_len--;settings_init();settings_get(&restored);assert(restored.log_heartbeat_min==DEFAULT_LOG_HEARTBEAT_MIN&&!restored.cloudflare.enabled);
 assert(settings_set(&c)==ESP_OK);settings_init();
 cloudflare_settings_t cf;settings_get_cloudflare(&cf);assert(!memcmp(&cf,&c.cloudflare,sizeof cf));
 for(unsigned i=0;i<=5;i++){cloudflare_settings_t x=cf;x.connections=i;assert(valid_cloudflare(&x)==(i>=1 && i<=4));}
 const char *bad[]={"https://bad.example","bad.example/path","bad\r\nHost: x","bad..host","-bad.host","bad-.host"};
 for(size_t i=0;i<sizeof bad/sizeof bad[0];i++){cloudflare_settings_t x=cf;strcpy(x.hostname,bad[i]);assert(!valid_cloudflare(&x));}
 cloudflare_settings_t invalid=cf;strcpy(invalid.token,"bad token with spaces");assert(!valid_cloudflare(&invalid));
 memset(invalid.token,'x',sizeof invalid.token);assert(!valid_cloudflare(&invalid));
 for(int remote=0;remote<=1;remote++) {
   httpd_req_t request={.user_ctx=remote?(void *)1:NULL};settings_get_handler(&request);assert(request.status==200);
   assert(!strstr(request.response,c.cloudflare.token));
   cJSON *j=cJSON_Parse(request.response);assert(j && cJSON_IsTrue(cJSON_GetObjectItem(j,"cloudflare_token_set")));
   assert(!cJSON_GetObjectItem(j,"cloudflare_token"));
   if(remote)assert(!cJSON_GetObjectItem(j,"google_sheets_secret"));
   cJSON_AddStringToObject(j,"cloudflare_token","");write_api(j,remote,200);
   cJSON_DeleteItemFromObject(j,"cloudflare_token");write_api(j,remote,200);cJSON_Delete(j);
   settings_get(&restored);assert(!strcmp(c.cloudflare.token,restored.cloudflare.token));
 }
 assert(wakes==0);
 cJSON *j=cJSON_CreateObject();settings_to_json(&c,j);
 cJSON_AddStringToObject(j,"cloudflare_token","YW5vdGhlci10ZXN0LXRva2Vu");write_api(j,false,200);assert(wakes==1);
 cJSON_ReplaceItemInObject(j,"cloudflare_connections",cJSON_CreateNumber(1.5));unsigned before=writes;write_api(j,false,400);assert(writes==before);
 cJSON_ReplaceItemInObject(j,"cloudflare_connections",cJSON_CreateNumber(4));
 cJSON_ReplaceItemInObject(j,"cloudflare_enabled",cJSON_CreateString("true"));write_api(j,false,400);assert(writes==before);
 cJSON_ReplaceItemInObject(j,"cloudflare_enabled",cJSON_CreateBool(false));write_api(j,false,200);assert(wakes==2);
 cJSON_DeleteItemFromObject(j,"cloudflare_token");cJSON_DeleteItemFromObject(j,"cloudflare_enabled");cJSON_DeleteItemFromObject(j,"cloudflare_hostname");cJSON_DeleteItemFromObject(j,"cloudflare_connections");write_api(j,false,200);assert(wakes==2);
 authenticated=false;httpd_req_t guest={.user_ctx=(void *)1};settings_get_handler(&guest);assert(guest.status==401);
 httpd_req_t device={0};settings_get_handler(&device);assert(device.status==200 && !strstr(device.response,"preserve-sheets"));
 write_api(j,false,401);write_api(j,true,401);configured=false;write_api(j,true,401);write_api(j,false,200);cJSON_Delete(j);
 fail_body_alloc=true;httpd_req_t oom={.content_len=2,.input="{}"};before=writes;settings_post_handler(&oom);assert(oom.status==500 && writes==before && !oom.received);fail_body_alloc=false;
 puts("PASS: v1/v2 migration, v3 roundtrip/corruption, preserved old blobs, unchanged credentials, Cloudflare persistence, 1–4 validation, host/token injection rejection, LAN/public redaction, blank/omitted token preservation, reconfiguration, auth and allocation failure");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'settings_test.c'
    binary = Path(directory) / 'settings_test'
    source.write_text(preamble + header + config + settings + serialization + post + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations', '-fsanitize=address,undefined', '-I', str(cjson), str(source), str(cjson / 'cJSON.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
