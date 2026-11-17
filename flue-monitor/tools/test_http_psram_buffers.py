"""Exercise actual login and OTA handlers with allocation and I/O failures."""
import subprocess
import tempfile
from pathlib import Path
from web_test_shim import native_source, body_reader

root = Path(__file__).resolve().parents[1]
api = native_source((root / 'main/rest_api.c').read_text(), tunnel='false')
auth = api[api.index('static esp_err_t auth_form_handler('):api.index('static const httpd_uri_t auth_login_uri')]
ota_source = (root.parent / 'components/ota_server/ota_server.c').read_text()
export = ota_source[ota_source.index('static esp_err_t history_export_handler('):ota_source.index('static esp_err_t history_restore_handler(')]
restore = ota_source[ota_source.index('static esp_err_t history_restore_handler('):ota_source.index('static esp_err_t ota_post_handler(')]
ota = ota_source[ota_source.index('static esp_err_t ota_post_handler('):ota_source.index('static const httpd_uri_t ota_uri')]
cjson = root / 'managed_components/espressif__cjson/cJSON'

preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define FLUE_TRACE(...) ((void)0)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 1
#define ESP_ERR_NOT_FOUND 2
#define ESP_ERR_TIMEOUT 3
#define ESP_ERR_INVALID_STATE 4
#define HTTPD_SOCK_ERR_TIMEOUT -2
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_401_UNAUTHORIZED 401
#define HTTPD_403_FORBIDDEN 403
#define HTTPD_404_NOT_FOUND 404
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define ESP_LOGI(tag,...) ((void)(tag), (void)snprintf(NULL,0,__VA_ARGS__))
#define ESP_LOGW(tag,...) ((void)(tag), (void)snprintf(NULL,0,__VA_ARGS__))
#define ESP_LOGE(tag,...) ((void)(tag), (void)snprintf(NULL,0,__VA_ARGS__))
#define pdMS_TO_TICKS(x) (x)
typedef struct {const char *uri,*input;size_t content_len;int received,status;} httpd_req_t;
static const char *TAG="test";
static bool fail_alloc,fail_read,timeout_once,timeout_always;
static int fail_read_after=-1;
static esp_err_t (*s_restore_history)(const char *,size_t);
static esp_err_t (*s_export_history)(void *,size_t *);
static unsigned boots,restores;
static bool bad_secret;
static unsigned exports;
static int export_history(void *body,size_t *n){if(!body){*n=4;return ESP_OK;}exports++;assert(*n==4);memcpy(body,"test",4);return ESP_OK;}
static int restore_history(const char *body,size_t n){assert(n==2 && !memcmp(body,"{}",2));restores++;return ESP_OK;}
static unsigned live_buffers,reads,logins;
static void *tracked_alloc(size_t size) {if(fail_alloc)return NULL;void *p=calloc(1,size);assert(p);live_buffers++;return p;}
static void tracked_free(void *p) {if(p){assert(live_buffers);live_buffers--;free(p);}}
#define free tracked_free
static void *buffer_memory_calloc(size_t n,size_t size) {return tracked_alloc(n*size);}
static void *buffer_memory_alloc(size_t size) {return tracked_alloc(size);}
static int httpd_req_recv(httpd_req_t *r,char *out,int amount) {
 reads++;if(timeout_always)return HTTPD_SOCK_ERR_TIMEOUT;
 if(fail_read_after>=0 && r->received>=fail_read_after)return -1;
 if(timeout_once){timeout_once=false;return HTTPD_SOCK_ERR_TIMEOUT;}
 if(fail_read)return -1;
 if(amount>137)amount=137; // force fragmented reads
 assert((size_t)(r->received+amount)<=r->content_len);
 memcpy(out,r->input+r->received,amount);r->received+=amount;return amount;
}
static int httpd_resp_send_err(httpd_req_t *r,int code,const char *text) {(void)text;r->status=code;return ESP_FAIL;}
static int httpd_resp_send(httpd_req_t *r,const void *body,size_t n){assert(n==4 && !memcmp(body,"test",4));r->status=200;return ESP_OK;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *text) {(void)text;if(!r->status)r->status=200;return ESP_OK;}
static int httpd_resp_set_type(httpd_req_t *r,const char *text) {(void)r;(void)text;return ESP_OK;}
static int httpd_resp_set_status(httpd_req_t *r,const char *text) {r->status=atoi(text);return ESP_OK;}
static int httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v) {(void)r;(void)k;(void)v;return ESP_OK;}
static bool auth_required(httpd_req_t *r) {(void)r;return false;}
static bool dashboard_auth_check_csrf(httpd_req_t *r) {(void)r;return true;}
static bool auth_setup_is_remote(httpd_req_t *r) {(void)r;return false;}
static bool dashboard_auth_is_configured(void) {return true;}
static int dashboard_auth_set_password(const char *a,const char *b) {(void)a;(void)b;return ESP_OK;}
static int auth_result, logout_result;
static int dashboard_auth_login(httpd_req_t *r,const char *password,bool remember) {
 (void)r;assert(!live_buffers);assert(!strcmp(password,"test-password"));assert(remember);logins++;return auth_result;
}
static int dashboard_auth_logout(httpd_req_t *r) {(void)r;return logout_result;}
typedef struct {const char *label;} esp_partition_t;
typedef int esp_ota_handle_t;
#define OTA_SIZE_UNKNOWN 0
static esp_partition_t partition={.label="test"};
static unsigned begins,aborts,writes,reboots;
static size_t written;
static bool fail_begin,fail_write,fail_end,fail_boot;
static const char *expected_image;
static bool secret_ok(httpd_req_t *r) {(void)r;return !bad_secret;}
static const esp_partition_t *esp_ota_get_running_partition(void) {return &partition;}
static const esp_partition_t *esp_ota_get_next_update_partition(void *p) {(void)p;return &partition;}
static int esp_ota_begin(const esp_partition_t *p,int n,esp_ota_handle_t *h) {(void)p;(void)n;begins++;*h=1;return fail_begin?ESP_FAIL:ESP_OK;}
static int esp_ota_write(esp_ota_handle_t h,const void *p,size_t n) {
 (void)h;assert(live_buffers==1 && n<=1024);assert(!memcmp(p,expected_image+written,n));
 writes++;if(fail_write)return ESP_FAIL;written+=n;return ESP_OK;
}
static int esp_ota_abort(esp_ota_handle_t h) {(void)h;aborts++;return ESP_OK;}
static int esp_ota_end(esp_ota_handle_t h) {(void)h;assert(!live_buffers);return fail_end?ESP_FAIL:ESP_OK;}
static int esp_ota_set_boot_partition(const esp_partition_t *p) {(void)p;assert(!live_buffers);boots++;return fail_boot?ESP_FAIL:ESP_OK;}
static const char *esp_err_to_name(int e) {(void)e;return "error";}
static void vTaskDelay(int ticks) {(void)ticks;}
static void esp_restart(void) {assert(!live_buffers);reboots++;}
'''
tests = r'''
int main(void) {
 const char *login="{\"password\":\"test-password\",\"remember\":true}";
 httpd_req_t r={.uri="/api/auth/login",.input=login,.content_len=(int)strlen(login)};
 fail_alloc=true;auth_form_handler(&r);assert(r.status==500 && !reads && !logins && !live_buffers);
 fail_alloc=false;fail_read=true;auth_form_handler(&r);assert(r.status==400 && !live_buffers);
 fail_read=false;timeout_once=true;reads=0;r.received=0;r.status=0;
 auth_form_handler(&r);assert(r.status==400 && reads==1 && !live_buffers);
 char partial[300];memset(partial,'x',sizeof partial);
 r=(httpd_req_t){.input=partial,.content_len=sizeof partial};fail_read_after=137;reads=0;
 assert(!web_read_body(&r,partial,sizeof partial) && reads==2);fail_read_after=-1;
 r=(httpd_req_t){.uri="/api/auth/login",.input=login,.content_len=strlen(login)};
 auth_form_handler(&r);assert(r.status==200 && logins==1 && !live_buffers);
 for(int error=0;error<2;error++) {
  auth_result=error?ESP_FAIL:ESP_ERR_INVALID_STATE;
  r=(httpd_req_t){.uri="/api/auth/login",.input=login,.content_len=(int)strlen(login)};
  auth_form_handler(&r);assert(r.status==(error?500:503)&&!live_buffers);
 }
 auth_result=ESP_OK;logout_result=ESP_FAIL;
 r=(httpd_req_t){.uri="/api/auth/logout",.input="{}",.content_len=2};
 auth_form_handler(&r);assert(r.status==500&&!live_buffers);logout_result=ESP_OK;
 r=(httpd_req_t){.uri="/api/auth/login",.input="{",.content_len=1};auth_form_handler(&r);assert(r.status==400 && !live_buffers);
 puts("PASS login: fragmented input, invalid JSON, receive/allocation failure and free before authentication");
 char image[2501];for(unsigned i=0;i<sizeof image;i++)image[i]=(char)i;expected_image=image;
 for(int mode=0;mode<7;mode++){
  fail_alloc=mode==1;fail_begin=mode==2;fail_read=mode==3;fail_write=mode==4;fail_end=mode==5;fail_boot=mode==6;
  begins=aborts=writes=reboots=0;written=reads=0;timeout_once=mode==0;
  r=(httpd_req_t){.input=image,.content_len=sizeof image};ota_post_handler(&r);
  assert(!live_buffers);
  if(mode==0)assert(r.status==200 && written==sizeof image && writes>2 && reboots==1 && !aborts);
  else {assert(r.status==500 && !reboots);if(mode==1)assert(!begins && !reads);if(mode==3 || mode==4)assert(aborts==1);}
 }
 timeout_always=true;reads=aborts=reboots=0;written=0;fail_boot=false;
 r=(httpd_req_t){.input=image,.content_len=sizeof image};ota_post_handler(&r);
 assert(r.status==500 && reads==4 && aborts==1 && !reboots && !live_buffers);
 timeout_always=false;
 puts("PASS OTA: exact fragmented image, timeout retry, allocation/begin/read/write/end/boot failures and complete cleanup");
 fail_alloc=fail_begin=fail_read=fail_write=fail_end=fail_boot=false;
 s_restore_history=restore_history;bad_secret=true;reads=0;
 r=(httpd_req_t){.input="{}",.content_len=2};history_restore_handler(&r);assert(r.status==401 && !reads && !restores);
 bad_secret=false;r=(httpd_req_t){.input="{}",.content_len=32769};history_restore_handler(&r);assert(r.status==400 && !restores);
 r=(httpd_req_t){.input="{}",.content_len=2};history_restore_handler(&r);assert(r.status==200 && restores==1 && !live_buffers);
 fail_alloc=true;r=(httpd_req_t){.input="{}",.content_len=2};history_restore_handler(&r);assert(r.status==500 && restores==1);
 fail_alloc=false;s_export_history=export_history;bad_secret=true;
 r=(httpd_req_t){0};history_export_handler(&r);assert(r.status==401 && !exports);
 bad_secret=false;r=(httpd_req_t){0};history_export_handler(&r);assert(r.status==200 && exports==1 && !live_buffers);
 fail_alloc=true;r=(httpd_req_t){0};history_export_handler(&r);assert(r.status==500 && exports==1 && !live_buffers);
 puts("PASS firmware update remains independent of graph backup, import/export authentication and bounded buffer cleanup");
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'http_test.c'
    binary = Path(directory) / 'http_test'
    source.write_text(preamble + body_reader() + auth + export + restore + ota + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-deprecated-declarations',
                    '-fsanitize=address,undefined', '-I', str(cjson), str(source),
                    str(cjson / 'cJSON.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
