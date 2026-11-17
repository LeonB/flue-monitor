"""ASan/UBSan test of actual detector, quiet hours, ntfy worker and HTTP actions."""
from pathlib import Path
from web_test_shim import body_reader
import re,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
def stripped(name):return re.sub(r'^#include .*$', '', (root/'main'/name).read_text(),flags=re.M).replace('#pragma once','')
preamble=r'''
#define _DARWIN_C_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <time.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_403_FORBIDDEN 403
#define HTTP_GET 0
#define HTTP_POST 1
#define HTTP_METHOD_POST 1
#define ESP_ERROR_CHECK(x) assert((x)==ESP_OK)
static int depth;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) do{(void)(x);assert(!depth);depth++;}while(0)
#define portEXIT_CRITICAL(x) do{(void)(x);assert(depth==1);depth--;}while(0)
static int64_t now_ms;
static time_t wall;
static int64_t esp_timer_get_time(void){return now_ms*1000;}
static time_t fake_time(time_t *out){if(out)*out=wall;return wall;}
#define time fake_time
typedef void *httpd_handle_t;
typedef struct {const char *uri;size_t content_len;size_t received;const char *input;int status;char output[512];} web_request_t;
typedef struct {const char *uri;int method;esp_err_t(*handler)(web_request_t*);} web_route_t;
static unsigned route_count;
static int web_register_handler(httpd_handle_t s,const web_route_t *r){(void)s;assert(r->uri&&r->handler);route_count++;return ESP_OK;}
static bool authenticated=true,csrf=true;
static bool dashboard_auth_check(web_request_t *r){(void)r;return authenticated;}
static bool dashboard_auth_check_csrf(web_request_t *r){(void)r;return csrf;}
static int web_set_status(web_request_t *r,const char *s){r->status=atoi(s);return ESP_OK;}
static int web_set_type(web_request_t *r,const char *s){(void)r;(void)s;return ESP_OK;}
static int web_set_header(web_request_t *r,const char *k,const char *v){(void)r;(void)k;(void)v;return ESP_OK;}
static int web_sendstr(web_request_t *r,const char *s){if(!r->status)r->status=200;snprintf(r->output,sizeof r->output,"%s",s);return ESP_OK;}
static int web_send_err(web_request_t *r,int code,const char *s){r->status=code;snprintf(r->output,sizeof r->output,"%s",s);return ESP_FAIL;}
static int web_recv(web_request_t *r,char *out,size_t n){if(n>1)n=1;memcpy(out,r->input+r->received,n);r->received+=n;return n;}
static int esp_crt_bundle_attach(void *p){(void)p;return ESP_OK;}
typedef struct {const char *url;int method,timeout_ms,buffer_size_tx;bool disable_auto_redirect;int(*crt_bundle_attach)(void*);} esp_http_client_config_t;
typedef void *esp_http_client_handle_t;
static bool fail_client,fail_perform,fail_header;
static int reply_status=200;
static unsigned sends,clients;
static char auth_header[144],post_body[192],destination[192],title_header[80],priority_header[20];
static void *esp_http_client_init(const esp_http_client_config_t *c){assert(!depth&&c->method==HTTP_METHOD_POST&&c->timeout_ms==10000&&c->disable_auto_redirect&&c->crt_bundle_attach);clients++;snprintf(destination,sizeof destination,"%s",c->url);return fail_client?NULL:(void*)1;}
static int esp_http_client_set_header(void *c,const char *k,const char *v){(void)c;if(fail_header)return ESP_FAIL;if(!strcmp(k,"Title"))snprintf(title_header,sizeof title_header,"%s",v);if(!strcmp(k,"Priority"))snprintf(priority_header,sizeof priority_header,"%s",v);if(!strcmp(k,"Authorization"))snprintf(auth_header,sizeof auth_header,"%s",v);return ESP_OK;}
static int esp_http_client_set_post_field(void *c,const char *s,size_t n){(void)c;assert(n<sizeof post_body);memcpy(post_body,s,n);post_body[n]=0;return ESP_OK;}
static int esp_http_client_perform(void *c){(void)c;assert(!depth);sends++;return fail_perform?ESP_FAIL:ESP_OK;}
static int esp_http_client_get_status_code(void *c){(void)c;return reply_status;}
static int esp_http_client_cleanup(void *c){(void)c;assert(!depth);return ESP_OK;}
'''
shims=r'''
static settings_t config;
static sensor_reading_t latest;
static void settings_get_refill(refill_settings_t *out){assert(!depth);*out=config.refill;}
float settings_get_burn_end_temperature(void){assert(!depth);return config.burn_end_temperature_c;}
static void sensors_get_last_reading(sensor_reading_t *out){assert(!depth);*out=latest;}
static bool thermocouple_reading_plausible(float c){return isfinite(c)&&c>=-40&&c<=600;}
'''
# Public declarations from the real headers remain compatible with host definitions.
shims=shims.replace('static void settings_get_refill','void settings_get_refill').replace('static void sensors_get_last_reading','void sensors_get_last_reading').replace('static bool thermocouple_reading_plausible','bool thermocouple_reading_plausible')
tests=r'''
static time_t local_time(int y,int m,int d,int h,int minute){struct tm t={.tm_year=y-1900,.tm_mon=m-1,.tm_mday=d,.tm_hour=h,.tm_min=minute,.tm_isdst=-1};return mktime(&t);}
static void reset_runtime(void){
 memset(&config,0,sizeof config);config.refill.enabled=1;config.refill.threshold_c=80;config.burn_end_temperature_c=60;
 config.refill.quiet_enabled=1;config.refill.quiet_start_min=1380;config.refill.quiet_end_min=420;
 strcpy(config.refill.url,"https://ntfy.example/unpredictable-test");strcpy(config.refill.token,"tk_test");strcpy(config.cloudflare.hostname,"stove.example");
 memset(&s_config,0,sizeof s_config);refill_rule_reset(&s_rule);s_pending=false;s_hot_latched=false;s_kind=JOB_REFILL;s_hot_temperature=0;s_override_until=0;s_generation=0;s_result="idle";s_http_status=0;
 now_ms=0;wall=local_time(2026,11,16,12,0);sends=clients=0;fail_client=fail_perform=fail_header=false;reply_status=200;
 latest=(sensor_reading_t){.thermocouple_ok=true};authenticated=csrf=true;
}
static void sample(float c,float rate){latest.thermocouple_c=c;latest.thermocouple_rate_c_per_min=rate;refill_notify_sample(&latest);now_ms+=10000;}
static void cycle(void){for(int i=0;i<=24;i++)sample(20+i*2,12);sample(160,10);for(int i=1;i<=40;i++)sample(160-i*2,-12);}
static web_request_t action(const char *uri){web_request_t r={.uri=uri,.content_len=2,.input="{}"};action_handler(&r);return r;}
int main(void){
 setenv("TZ","CET-1CEST,M3.5.0,M10.5.0/3",1);tzset();
 assert(!refill_quiet_minute(1379,1380,420)&&refill_quiet_minute(1380,1380,420));
 assert(refill_quiet_minute(419,1380,420)&&!refill_quiet_minute(420,1380,420));
 assert(refill_quiet_minute(600,540,1020)&&!refill_quiet_minute(1020,540,1020));
 // Compare compact Netherlands conversion with libc's full EU TZ rules.
 for(int y=2026;y<=2035;y++)for(int m=1;m<=12;m++)for(int d=1;d<=31;d++)for(int h=0;h<24;h+=6) {
  time_t epoch=local_time(y,m,d,h,15);struct tm local;localtime_r(&epoch,&local);
  assert(refill_local_minute(epoch)==local.tm_hour*60+local.tm_min);
 }
 time_t spring=local_time(2026,3,28,23,30);
 assert(refill_next_quiet_end(spring,150)==local_time(2026,3,29,3,0));
 reset_runtime();refill_notify_register(NULL);assert(route_count==4);
 // Stable/cooling samples cannot arm; a real cycle sends exactly once.
 for(int i=0;i<100;i++)sample(50,-1);assert(!s_pending);
 cycle();assert(s_pending);refill_notify_send_pending(&config);assert(sends==1&&!strcmp(s_result,"sent"));
 assert(!strcmp(destination,config.refill.url)&&!strcmp(auth_header,"Bearer tk_test"));
 for(int i=0;i<30;i++){sample(70,-1);refill_notify_send_pending(&config);}assert(sends==1);
 cycle();refill_notify_send_pending(&config);assert(sends==2);
 // A manual refill cancels pending work, irrespective of Sheets availability.
 reset_runtime();cycle();refill_notify_manual_event("added_wood");refill_notify_send_pending(&config);assert(!s_pending&&!sends);

 // An action starts a session, but unchanged/cooling heat cannot rearm it.
 reset_runtime();sample(74,-1);refill_notify_manual_event("added_wood");
 assert(s_rule.session_active&&s_rule.action_pending&&!s_rule.armed);
 for(int i=0;i<60;i++)sample(66,-0.1f);assert(!s_pending&&!s_rule.armed);
 // Short measured recovery: +20 C after the trough, without four fast minutes.
 sample(75,0.8f);sample(86,3);assert(s_rule.armed&&!s_rule.action_pending);
 sample(116,2.73f);refill_notify_manual_event("damper_down");assert(s_rule.armed);
 for(int i=0;i<31;i++)sample(83,-1);assert(!s_pending);
 sample(80,-0.5f);assert(s_pending);refill_notify_send_pending(&config);assert(sends==1);
 for(int i=0;i<40;i++)sample(70,-0.5f);assert(!s_pending&&s_rule.session_active);
 // Actions during initial config/without any sample survive to the first sample.
 reset_runtime();refill_notify_manual_event("cold_start");sample(20,0);
 sample(39,1);assert(!s_rule.armed);sample(40,1);assert(s_rule.armed);
 // Repeated actions restart the evidence; no reused peak or stale baseline.
 refill_notify_manual_event("added_wood");sample(40,0);assert(!s_rule.armed);
 sample(59,1);assert(!s_rule.armed);sample(60,1);assert(s_rule.armed);
 refill_notify_manual_event("stove_off");assert(!s_rule.session_active&&!s_rule.armed&&!s_rule.action_pending);
 for(int i=0;i<40;i++)sample(50,-1);assert(!s_pending);
 // Thirty cold minutes without sustained warming expire even an action session.
 reset_runtime();sample(30,0);refill_notify_manual_event("cold_start");
 for(int i=0;i<=180;i++)sample(30,0);assert(!s_rule.session_active&&!s_rule.action_pending);
 sample(55,1);assert(!s_rule.armed); // old action cannot arm a later rise
 // The configured session end is used, rather than a hardcoded 60 C boundary.
 reset_runtime();config.burn_end_temperature_c=40;sample(50,0);refill_notify_manual_event("added_wood");
 for(int i=0;i<200;i++)sample(50,0);assert(s_rule.session_active&&s_rule.action_pending);
 // Missing/invalid samples discard manual evidence just like automatic evidence.
 now_ms+=40000;sample(75,1);assert(!s_rule.armed&&!s_rule.action_pending);
 refill_notify_manual_event("added_wood");latest.thermocouple_ok=false;sample(80,0);
 assert(!s_rule.session_active&&!s_rule.action_pending);
 reset_runtime();config.refill.enabled=0;refill_notify_manual_event("cold_start");assert(!s_rule.session_active);

 // Quiet candidates are discarded permanently; morning does not release them.
 reset_runtime();wall=local_time(2026,11,16,23,30);cycle();assert(!s_pending&&!strcmp(s_result,"quiet"));
 wall=local_time(2026,11,17,7,0);refill_notify_send_pending(&config);sample(70,-1);assert(!s_pending&&!sends);
 // Re-check quiet hours, expiry, sensor validity and config before transport.
 reset_runtime();cycle();wall=local_time(2026,11,16,23,0);refill_notify_send_pending(&config);assert(!sends);
 reset_runtime();cycle();now_ms+=120001;refill_notify_send_pending(&config);assert(!sends);
 reset_runtime();cycle();latest.thermocouple_ok=false;refill_notify_send_pending(&config);assert(!sends);
 reset_runtime();cycle();latest.thermocouple_rate_c_per_min=3;refill_notify_send_pending(&config);assert(!sends);
 reset_runtime();cycle();strcpy(config.refill.url,"https://ntfy.example/replacement");refill_notify_send_pending(&config);assert(!sends);
 reset_runtime();cycle();refill_notify_manual_event("stove_off");refill_notify_send_pending(&config);assert(!sends);
 // Ambiguous timeouts and non-2xx statuses never produce duplicate retries.
 reset_runtime();cycle();fail_perform=true;refill_notify_send_pending(&config);refill_notify_send_pending(&config);assert(sends==1&&!strcmp(s_result,"failed"));
 reset_runtime();cycle();reply_status=403;refill_notify_send_pending(&config);assert(sends==1&&!strcmp(s_result,"failed")&&s_http_status==403);
 reset_runtime();cycle();fail_client=true;refill_notify_send_pending(&config);assert(!sends&&!strcmp(s_result,"failed"));
 reset_runtime();cycle();fail_header=true;refill_notify_send_pending(&config);assert(!sends&&!strcmp(s_result,"failed"));
 // Explicit test bypasses quiet hours. User actions require authentication+CSRF.
 reset_runtime();wall=local_time(2026,11,16,23,30);web_request_t r=action("/api/refill/test");assert(r.status==200);
 refill_notify_send_pending(&config);assert(sends==1&&strstr(post_body,"Testmelding"));
 r=(web_request_t){0};status_handler(&r);assert(!strstr(r.output,"ntfy.example")&&!strstr(r.output,"tk_test"));
 authenticated=false;r=action("/api/refill/test");assert(r.status==401);r=(web_request_t){0};status_handler(&r);assert(r.status==401);
 authenticated=true;csrf=false;r=action("/api/refill/allow-tonight");assert(r.status==403);csrf=true;
 // One-night override expires at the next end, even across both DST changes.
 reset_runtime();wall=local_time(2026,3,28,23,30);r=action("/api/refill/allow-tonight");assert(r.status==200&&s_override_until-wall==23400);
 cycle();refill_notify_send_pending(&config);assert(sends==1);
 wall=s_override_until+16*3600;cycle();assert(!s_pending);
 reset_runtime();wall=local_time(2026,10,24,23,30);r=action("/api/refill/allow-tonight");assert(r.status==200&&s_override_until-wall==30600);
 r=action("/api/refill/quiet");assert(r.status==200&&!s_override_until);
 // Missing clock never delivers. Settings disabled always disarms.
 reset_runtime();wall=0;cycle();assert(!s_pending);r=action("/api/refill/test");assert(r.status==400);
 reset_runtime();config.refill.enabled=0;cycle();assert(!s_pending);
 // Invalid samples/recording gaps break a partially observed warming sequence.
 reset_runtime();for(int i=0;i<15;i++)sample(40+i,4);latest.thermocouple_ok=false;sample(60,4);latest.thermocouple_ok=true;
 for(int i=0;i<15;i++)sample(70+i,4);assert(!s_rule.armed);now_ms+=40000;sample(100,4);assert(!s_rule.armed);
 // An action cannot survive a delayed first sample with no fresh baseline.
 reset_runtime();refill_notify_manual_event("cold_start");now_ms+=40000;sample(30,0);
 assert(!s_rule.action_pending&&!s_rule.session_active);
 // Overheat is independent of warming, refill enable and quiet hours.
 reset_runtime();config.refill.enabled=0;wall=local_time(2026,11,16,23,30);
 sample(200,0);assert(!s_pending);sample(200.1f,NAN);assert(s_pending&&s_kind==JOB_HOT);
 sample(205,1);refill_notify_send_pending(&config);
 assert(sends==1&&!strcmp(s_result,"sent")&&strstr(post_body,"205.0")&&strstr(post_body,"boven 200"));
 assert(!strcmp(title_header,"Flue Monitor - te heet")&&!strcmp(priority_header,"high"));
 r=(web_request_t){0};status_handler(&r);assert(strstr(r.output,"overheat")&&strstr(r.output,"true"));
 // Threshold chatter does not repeat; strictly below 190 rearms.
 sample(199,-1);sample(220,1);refill_notify_send_pending(&config);assert(sends==1);
 sample(190,-1);sample(201,1);refill_notify_send_pending(&config);assert(sends==1);
 sample(189,-1);sample(201,1);refill_notify_send_pending(&config);assert(sends==2);
 // A hot reading preempts a refill/test and cannot be cancelled by manual events.
 reset_runtime();cycle();assert(s_pending&&s_kind==JOB_REFILL);sample(210,5);assert(s_kind==JOB_HOT);
 refill_notify_manual_event("added_wood");refill_notify_manual_event("cold_start");refill_notify_manual_event("stove_off");assert(s_pending);
 r=action("/api/refill/test");assert(r.status==400&&s_pending&&s_kind==JOB_HOT);
 config.refill.enabled=0;config.refill.quiet_end_min=480;sample(211,5);assert(s_pending);
 // Deliver the captured peak even if the fire has cooled or the sensor then fails.
 latest.thermocouple_ok=false;refill_notify_send_pending(&config);assert(sends==1&&strstr(post_body,"211.0"));
 reset_runtime();r=action("/api/refill/test");sample(210,0);assert(s_kind==JOB_HOT);
 refill_notify_send_pending(&config);assert(sends==1&&!strstr(post_body,"Testmelding"));
 // Invalid values never trigger; a valid overheat waits briefly for SNTP at boot.
 reset_runtime();latest.thermocouple_ok=false;sample(220,0);assert(!s_pending);latest.thermocouple_ok=true;
 sample(NAN,0);sample(601,0);assert(!s_pending);wall=0;sample(210,0);
 refill_notify_send_pending(&config);assert(s_pending&&!sends);
 wall=local_time(2026,11,16,23,30);refill_notify_send_pending(&config);assert(!s_pending&&sends==1);
 reset_runtime();sample(210,0);now_ms+=120001;refill_notify_send_pending(&config);assert(!sends&&!s_pending);
 // Destination changes cancel old work; the new receiver gets the next hot sample.
 reset_runtime();sample(210,0);strcpy(config.refill.url,"https://ntfy.example/new");
 refill_notify_send_pending(&config);assert(!sends);sample(210,0);refill_notify_send_pending(&config);
 assert(sends==1&&!strcmp(destination,"https://ntfy.example/new"));
 // Failed transport is one attempt, not an endless stream of warnings.
 reset_runtime();sample(210,0);fail_perform=true;refill_notify_send_pending(&config);sample(211,0);
 refill_notify_send_pending(&config);assert(sends==1&&!strcmp(s_result,"failed"));
 puts("PASS overheat >200, rearm <190, priority/preemption, quiet/off bypass, clock wait, sensor validation, captured peak and destination changes; refill detector/rearm, manual cancellation, quiet hours/no morning catch-up, DST override, ntfy headers/HTTPS/timeout, failure/no duplicates, stale/invalid reading, auth+CSRF and redacted status");
}
'''
with tempfile.TemporaryDirectory() as d:
    source=Path(d)/'refill.c';binary=Path(d)/'refill'
    source.write_text(preamble+stripped('settings.h')+stripped('sensors.h')+stripped('refill_rule.h')+shims+body_reader(native=False)+stripped('refill_rule.c')+stripped('refill_notify.c')+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
