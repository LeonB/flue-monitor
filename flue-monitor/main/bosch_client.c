// POINTT protocol based on CaseyRo/ha_bosch; no Bosch resource writes.
#include "bosch_client.h"
#include "bosch_protocol.h"
#include "dashboard_auth.h"
#include "buffer_memory.h"
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include "psa/crypto.h"
#include "mbedtls/base64.h"
#include <stdlib.h>
#include <stdio.h>
#include <time.h>

#define CLIENT_ID "762162C0-FA2D-4540-AE66-6489F189FADC"
#define TOKEN_URL "https://singlekey-id.com/auth/connect/token"
#define API_ROOT "https://pointt-api.bosch-thermotechnology.com/pointt-api/api/v1/gateways/"
// Match the proven community client's scopes. The worker uses GET only for resources.
#define SCOPES "openid email profile offline_access pointt.gateway.claiming pointt.gateway.removal pointt.gateway.list pointt.gateway.users pointt.gateway.resource.dashapp pointt.castt.flow.token-exchange bacon"
#define RESPONSE_MAX 24576
#define TOKEN_MAX 8192
#define REFRESH_MAX 4096
#define AUTH_MAX 2304

static SemaphoreHandle_t lock;
static QueueHandle_t jobs;
static TaskHandle_t worker;
static struct {
    char state[24], error[128], device[64], zone[7];
    char *auth_url;
    char zones[32][7];
    unsigned zone_count;
    bool linked, available, busy;
    double temperature;
    int64_t sampled, auth_deadline;
    unsigned polls, refreshes;
} status;
// Only the worker accesses credentials. Never serialized in status or readings.
static char *access_token, *refresh_token;
static char device[64], zone[7] = "zn1", verifier[65], oauth_state[65];
static int64_t expiry, auth_deadline;
static bool reauth;
static char zones_device[64];
static int64_t zones_next;
static int http_status;

static int64_t now_s(void) { return esp_timer_get_time()/1000000; }
static void wipe_free(char *s) {
    if (!s) return;
    volatile char *p = s; size_t n = strlen(s); while (n--) *p++ = 0;
    free(s);
}
static char *copy_string(const char *s, size_t max) {
    if (!s || !*s || strlen(s) > max) return NULL;
    char *p = buffer_memory_alloc(strlen(s)+1);
    if (p) strcpy(p, s);
    return p;
}
static const char *jstr(cJSON *o, const char *key) {
    cJSON *v = cJSON_GetObjectItemCaseSensitive(o,key);
    return cJSON_IsString(v) ? v->valuestring : "";
}
static void set_status(const char *state, const char *error) {
    xSemaphoreTake(lock, portMAX_DELAY);
    snprintf(status.state,sizeof status.state,"%s",state);
    snprintf(status.error,sizeof status.error,"%s",error ? error : "");
    status.linked = refresh_token != NULL;
    snprintf(status.device,sizeof status.device,"%s",device);
    snprintf(status.zone,sizeof status.zone,"%s",zone);
    if (strcmp(state,"connected")) status.available = false;
    xSemaphoreGive(lock);
}
static char *encode(const char *s) {
    size_t n = strlen(s);
    char *out = buffer_memory_alloc(3*n+1); if (!out) return NULL;
    char *p = out;
    for (; *s; s++) {
        unsigned char c = *s;
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || strchr("-._~", c)) *p++ = c;
        else { sprintf(p,"%%%02X",c); p += 3; }
    }
    *p = 0; return out;
}
static char *form(const char **pairs, size_t count) {
    size_t cap = 1;
    for (size_t i=0;i<count;i++) cap += strlen(pairs[i])*3+2;
    char *out = buffer_memory_calloc(cap,1); if (!out) return NULL;
    for (size_t i=0;i<count;i++) {
        char *s = encode(pairs[i]);
        if (!s) { wipe_free(out); return NULL; }
        strcat(out,s); wipe_free(s);
        strcat(out,i%2 ? (i+1<count ? "&" : "") : "=");
    }
    return out;
}
static void random_hex(char out[65]) {
    uint8_t bytes[32]; esp_fill_random(bytes,sizeof bytes);
    for (int i=0;i<32;i++) sprintf(out+i*2,"%02x",bytes[i]);
}

// Bound responses even for chunked bodies and refuse redirects (credentials must
// never be forwarded to another host). TLS always verifies the full root bundle.
typedef struct { char *data; size_t size; bool overflow; } response_t;
static esp_err_t http_event(esp_http_client_event_t *evt) {
    response_t *r = evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA && evt->data_len > 0) {
        if (r->size + evt->data_len >= RESPONSE_MAX) { r->overflow = true; return ESP_FAIL; }
        memcpy(r->data+r->size,evt->data,evt->data_len); r->size += evt->data_len;
    }
    return ESP_OK;
}
static char request_failure[80];
static const char *request_stage = "Bosch request";
static cJSON *request(const char *url, const char *body, bool authorized) {
    http_status = 0;
    strcpy(request_failure,"Insufficient memory");
    if (time(NULL) < 1700000000) { strcpy(request_failure,"Waiting for clock synchronization"); return NULL; } // Wait for SNTP before TLS.
    response_t r = {.data=buffer_memory_calloc(RESPONSE_MAX,1)};
    if (!r.data) return NULL;
    esp_http_client_config_t config = {.url=url, .timeout_ms=15000,
        .crt_bundle_attach=esp_crt_bundle_attach, .disable_auto_redirect=true,
        .event_handler=http_event,.user_data=&r,.buffer_size=1024,
        // ESP-IDF requires each header to fit in the TX buffer. OAuth JWTs
        // exceed its 512-byte default; reserve space for Bearer and framing.
        .buffer_size_tx=authorized && access_token ? (int)strlen(access_token)+256 : 512};
    esp_http_client_handle_t h = esp_http_client_init(&config);
    cJSON *result = NULL;
    if (!h) goto done;
    esp_http_client_set_header(h,"Accept","application/json");
    if (authorized) {
        if (!access_token) goto cleanup;
        char *bearer = buffer_memory_alloc(strlen(access_token)+8);
        if (!bearer) goto cleanup;
        sprintf(bearer,"Bearer %s",access_token);
        esp_err_t err = esp_http_client_set_header(h,"Authorization",bearer);
        wipe_free(bearer); if (err != ESP_OK) goto cleanup;
    }
    if (body) {
        esp_http_client_set_method(h,HTTP_METHOD_POST);
        esp_http_client_set_header(h,"Content-Type","application/x-www-form-urlencoded");
        esp_http_client_set_post_field(h,body,strlen(body));
    }
    esp_err_t transport = esp_http_client_perform(h);
    http_status = esp_http_client_get_status_code(h);
    if (r.overflow) strcpy(request_failure,"Response exceeds 24 KiB limit");
    else if (transport != ESP_OK)
        snprintf(request_failure,sizeof request_failure,"Network/TLS error 0x%x",(unsigned)transport);
    else if (http_status != 200)
        snprintf(request_failure,sizeof request_failure,"HTTP %d",http_status);
    else {
        result = cJSON_ParseWithLength(r.data,r.size+1);
        snprintf(request_failure,sizeof request_failure,"%s",result ? "" : "Invalid JSON response");
    }
cleanup:
    esp_http_client_cleanup(h);
done:
    wipe_free(r.data);
    return result;
}

// One NVS value makes refresh-token rotation + device/zone persistence atomic.
static bool save_credentials(void) {
    cJSON *o = cJSON_CreateObject();
    if (!o) return false;
    bool ok = cJSON_AddStringToObject(o,"refresh",refresh_token ? refresh_token : "") &&
        cJSON_AddStringToObject(o,"device",device) && cJSON_AddStringToObject(o,"zone",zone);
    char *json = ok ? cJSON_PrintUnformatted(o) : NULL;
    cJSON_Delete(o); if (!json) return false;
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("bosch",NVS_READWRITE,&nvs);
    if (err == ESP_OK) { err = nvs_set_str(nvs,"credentials",json); if (err == ESP_OK) err = nvs_commit(nvs); nvs_close(nvs); }
    wipe_free(json); return err == ESP_OK;
}
static void load_credentials(void) {
    nvs_handle_t nvs; size_t size=0;
    if (nvs_open("bosch",NVS_READONLY,&nvs) != ESP_OK) return;
    if (nvs_get_str(nvs,"credentials",NULL,&size) == ESP_OK && size <= REFRESH_MAX+256) {
        char *json = buffer_memory_calloc(size,1);
        if (json && nvs_get_str(nvs,"credentials",json,&size) == ESP_OK) {
            cJSON *o = cJSON_Parse(json);
            const char *d=jstr(o,"device"), *z=jstr(o,"zone");
            if ((!*d || bosch_id_valid(d)) && bosch_zone_valid(z)) {
                refresh_token=copy_string(jstr(o,"refresh"),REFRESH_MAX);
                snprintf(device,sizeof device,"%s",d); snprintf(zone,sizeof zone,"%s",z);
            }
            cJSON_Delete(o);
        }
        wipe_free(json);
    }
    nvs_close(nvs);
}
static bool accept_tokens(cJSON *o) {
    char *a=copy_string(jstr(o,"access_token"),TOKEN_MAX);
    const char *next_refresh = jstr(o,"refresh_token");
    char *r=copy_string(*next_refresh ? next_refresh : refresh_token,REFRESH_MAX);
    cJSON *seconds=cJSON_GetObjectItemCaseSensitive(o,"expires_in");
    if (!a || !r || !cJSON_IsNumber(seconds) || seconds->valuedouble < 60 || seconds->valuedouble > 86400) {
        wipe_free(a); wipe_free(r); return false;
    }
    bool changed = !refresh_token || strcmp(r,refresh_token);
    wipe_free(access_token); wipe_free(refresh_token); access_token=a; refresh_token=r;
    expiry=now_s()+(int)seconds->valuedouble; reauth=false;
    if (changed && !save_credentials()) {
        set_status("storage_error","Could not save refreshed credentials. Reconnect after checking storage.");
        reauth=true; return false;
    }
    return true;
}
static bool refresh(void) {
    const char *pairs[]={"grant_type","refresh_token","refresh_token",refresh_token,"client_id",CLIENT_ID,"scope",SCOPES};
    char *body=form(pairs,8); if (!body) return false;
    cJSON *o=request(TOKEN_URL,body,false); wipe_free(body);
    bool ok=o && accept_tokens(o); cJSON_Delete(o);
    if (ok) { xSemaphoreTake(lock,portMAX_DELAY); status.refreshes++; xSemaphoreGive(lock); }
    else if (http_status==400 || http_status==401 || http_status==403) reauth=true;
    return ok;
}
static void clear_login(void) {
    verifier[0]=oauth_state[0]=0; auth_deadline=0;
    xSemaphoreTake(lock,portMAX_DELAY);
    free(status.auth_url); status.auth_url=NULL; status.auth_deadline=0;
    xSemaphoreGive(lock);
}
static bool begin_login(void) {
    clear_login(); random_hex(verifier); random_hex(oauth_state);
    uint8_t digest[32]; size_t n=0; char challenge[48], nonce[65];
    random_hex(nonce);
    if (psa_hash_compute(PSA_ALG_SHA_256,(uint8_t *)verifier,strlen(verifier),digest,sizeof digest,&n)!=PSA_SUCCESS) return false;
    if (mbedtls_base64_encode((unsigned char *)challenge,sizeof challenge,&n,digest,sizeof digest)) return false;
    for (size_t i=0;i<n;i++) { if (challenge[i]=='+') challenge[i]='-'; if (challenge[i]=='/') challenge[i]='_'; if (challenge[i]=='=') challenge[i]=0; }
    const char *pairs[]={"redirect_uri",BOSCH_REDIRECT,"client_id",CLIENT_ID,"response_type","code",
        "prompt","login","state",oauth_state,"nonce",nonce,"scope",SCOPES,"code_challenge",challenge,
        "code_challenge_method","S256","style_id","tt_bsch","suppressed_prompt","login"};
    char *query=form(pairs,22); if (!query) return false;
    char *ret=buffer_memory_alloc(strlen(query)+40);
    if (!ret) { free(query); return false; }
    sprintf(ret,"/auth/connect/authorize/callback?%s",query); free(query);
    char *encoded=encode(ret); free(ret); if (!encoded) return false;
    char *url=buffer_memory_alloc(strlen(encoded)+70);
    if (url) sprintf(url,"https://singlekey-id.com/auth/en-us/login?ReturnUrl=%s",encoded);
    free(encoded);
    if (!url || strlen(url)>=AUTH_MAX) { free(url); return false; }
    auth_deadline=now_s()+1200;
    xSemaphoreTake(lock,portMAX_DELAY); status.auth_url=url; status.auth_deadline=auth_deadline; xSemaphoreGive(lock);
    set_status("awaiting_login",NULL); return true;
}
static bool discover(void) {
    if (*device) return true;
    cJSON *o=request(API_ROOT,NULL,true);
    if (!o) {
        if (http_status==401) expiry=0;
        if (http_status==403) reauth=true;
        return false;
    }
    bool ok=cJSON_IsArray(o) && cJSON_GetArraySize(o)==1;
    const char *id=ok ? jstr(cJSON_GetArrayItem(o,0),"deviceId") : "";
    ok=bosch_id_valid(id);
    if (ok) snprintf(device,sizeof device,"%s",id);
    cJSON_Delete(o);
    if (!ok) { set_status("select_device","Enter the thermostat serial number and save the selection."); return false; }
    return save_credentials();
}
// Discovery is cached independently of temperature; a failed optional listing
// must not hide a successful room reading. Never follow arbitrary cloud URLs.
static void discover_zones(void) {
    if (strcmp(zones_device, device)) {
        strcpy(zones_device, device); zones_next=0;
        xSemaphoreTake(lock,portMAX_DELAY); status.zone_count=0; xSemaphoreGive(lock);
    }
    if (now_s()<zones_next) return;
    zones_next=now_s()+600;
    char url[256]; snprintf(url,sizeof url,API_ROOT "%s/resource/zones",device);
    cJSON *o=request(url,NULL,true);
    cJSON *refs=cJSON_GetObjectItemCaseSensitive(o,"references");
    if (cJSON_IsArray(refs)) {
        xSemaphoreTake(lock,portMAX_DELAY); status.zone_count=0;
        cJSON *item;
        cJSON_ArrayForEach(item,refs) {
            const char *id=jstr(item,"id");
            if (strncmp(id,"/zones/",7) || !bosch_zone_valid(id+7)) continue;
            bool duplicate=false;
            for (unsigned i=0;i<status.zone_count;i++) if (!strcmp(status.zones[i],id+7)) duplicate=true;
            if (!duplicate && status.zone_count<32) strcpy(status.zones[status.zone_count++],id+7);
        }
        xSemaphoreGive(lock);
    }
    cJSON_Delete(o);
}
static bool poll_temperature(void) {
    request_stage="Token refresh";
    if ((!access_token || now_s()>=expiry-60) && !refresh()) return false;
    request_stage="Thermostat discovery";
    if (!discover()) return false;
    discover_zones();
    char url[256]; snprintf(url,sizeof url,API_ROOT "%s/resource/zones/%s/temperatureActual",device,zone);
    request_stage="Room temperature";
    cJSON *o=request(url,NULL,true);
    if (!o) {
        if (http_status==401) { expiry=0; wipe_free(access_token); access_token=NULL; }
        if (http_status==403) reauth=true;
        return false;
    }
    cJSON *v=cJSON_GetObjectItemCaseSensitive(o,"value");
    bool ok=cJSON_IsNumber(v) && bosch_temperature_valid(v->valuedouble);
    if (ok) {
        xSemaphoreTake(lock,portMAX_DELAY); status.temperature=v->valuedouble;
        status.sampled=now_s(); status.available=true; status.polls++; xSemaphoreGive(lock);
        set_status("connected",NULL);
    } else set_status("invalid_reading","This zone has no valid room temperature. Select another zone.");
    cJSON_Delete(o); return ok;
}
static void command(cJSON *o) {
    const char *action=jstr(o,"action");
    if (!strcmp(action,"start")) {
        if (!begin_login()) set_status("error","Could not create sign-in link.");
    } else if (!strcmp(action,"callback")) {
        char code[1024];
        if (now_s()>=auth_deadline || !bosch_callback(jstr(o,"callback"),oauth_state,code,sizeof code)) {
            set_status("login_error","Link expired or belongs to an earlier sign-in. Click Connect to Bosch and use the new return link."); return;
        }
        const char *pairs[]={"grant_type","authorization_code","code",code,"client_id",CLIENT_ID,
            "redirect_uri",BOSCH_REDIRECT,"code_verifier",verifier,"scope",SCOPES};
        char *body=form(pairs,12); memset(code,0,sizeof code);
        if (!body) { set_status("error","Insufficient memory."); return; }
        cJSON *tokens=request(TOKEN_URL,body,false); wipe_free(body);
        // A new authorization must supply its own refresh token, never reuse an
        // existing account's token when the token response is incomplete.
        bool ok=tokens && *jstr(tokens,"refresh_token") && accept_tokens(tokens);
        cJSON_Delete(tokens);
        if (ok) { clear_login(); device[0]=0; zones_device[0]=0; if (!save_credentials()) { reauth=true; set_status("storage_error","Could not save credentials."); } else set_status("connecting",NULL); }
        else set_status("login_error","Token exchange failed. Start a new Bosch sign-in.");
    } else if (!strcmp(action,"select")) {
        const char *d=jstr(o,"device"), *z=jstr(o,"zone");
        if ((*d && !bosch_id_valid(d)) || !bosch_zone_valid(z)) { set_status("error","Invalid serial number or zone."); return; }
        char old_device[64], old_zone[7]; strcpy(old_device,device); strcpy(old_zone,zone);
        strcpy(device,d); strcpy(zone,z);
        if (!save_credentials()) { strcpy(device,old_device); strcpy(zone,old_zone); set_status("storage_error","Could not save selection."); }
        else set_status(refresh_token ? "connecting" : "disconnected",NULL);
    } else if (!strcmp(action,"disconnect")) {
        nvs_handle_t nvs; esp_err_t err=nvs_open("bosch",NVS_READWRITE,&nvs);
        if (err==ESP_OK) { err=nvs_erase_key(nvs,"credentials"); if (err==ESP_ERR_NVS_NOT_FOUND) err=ESP_OK; if (err==ESP_OK) err=nvs_commit(nvs); nvs_close(nvs); }
        if (err!=ESP_OK) { set_status("storage_error","Could not remove saved credentials."); return; }
        clear_login(); wipe_free(access_token); access_token=NULL; wipe_free(refresh_token); refresh_token=NULL;
        device[0]=0; zones_device[0]=0; reauth=false;
        xSemaphoreTake(lock,portMAX_DELAY); status.zone_count=0; xSemaphoreGive(lock);
        set_status("disconnected",NULL);
    }
}
bool bosch_client_get_temperature(double *temperature_c) {
    if (!lock || !temperature_c) return false;
    xSemaphoreTake(lock,portMAX_DELAY);
    bool valid=status.linked && status.available && now_s()-status.sampled<=180 &&
        bosch_temperature_valid(status.temperature);
    if (valid) *temperature_c=status.temperature;
    xSemaphoreGive(lock);
    return valid;
}
static void task(void *arg) {
    load_credentials(); set_status(refresh_token ? "connecting" : "disconnected",NULL);
    int64_t next=0; unsigned retry=30;
    for (;;) {
        char *body=NULL;
        if (xQueueReceive(jobs,&body,pdMS_TO_TICKS(1000))==pdTRUE) {
            cJSON *o=cJSON_Parse(body); wipe_free(body);
            command(o); cJSON_Delete(o);
            xSemaphoreTake(lock,portMAX_DELAY); status.busy=false; xSemaphoreGive(lock);
            next=now_s()+1; retry=30;
        }
        if (auth_deadline && now_s()>=auth_deadline) { clear_login(); set_status("login_error","Sign-in link expired. Start again."); }
        if (refresh_token && !reauth && !auth_deadline && now_s()>=next) {
            // Keep handlers responsive: no mutex is held during network I/O.
            if (poll_temperature()) { retry=30; next=now_s()+60; }
            else {
                xSemaphoreTake(lock,portMAX_DELAY);
                bool specific=!strcmp(status.state,"select_device") || !strcmp(status.state,"invalid_reading") || !strcmp(status.state,"storage_error");
                xSemaphoreGive(lock);
                if (!specific) {
                    char message[128];
                    snprintf(message,sizeof message,"%s: %s. %s",request_stage,request_failure,
                        reauth ? "Connect again." : "Retrying automatically.");
                    set_status(reauth ? "reauth_required" : "retrying",message);
                }
                next=now_s()+retry; retry=retry<450 ? retry*2 : 900;
            }
        }
    }
}
static esp_err_t unavailable(httpd_req_t *req, const char *message) {
    httpd_resp_set_status(req,"503 Service Unavailable");
    return httpd_resp_sendstr(req,message);
}
static esp_err_t handler(httpd_req_t *req) {
    httpd_resp_set_hdr(req,"Cache-Control","no-store");
    if (!dashboard_auth_check(req)) return httpd_resp_send_err(req,HTTPD_401_UNAUTHORIZED,"Sign in required");
    if (!worker) return unavailable(req,"Bosch worker unavailable");
    if (req->method==HTTP_POST) {
        if (!dashboard_auth_check_csrf(req)) return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Invalid request origin");
        if (req->content_len<=0 || req->content_len>=2048) return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Body too large");
        char *body=buffer_memory_calloc(req->content_len+1,1);
        if (!body) return unavailable(req,"Insufficient memory");
        int count=0;
        while (count<req->content_len) {
            int n=httpd_req_recv(req,body+count,req->content_len-count);
            if (n<=0) { wipe_free(body); return httpd_resp_send_err(req,HTTPD_408_REQ_TIMEOUT,"Incomplete request"); }
            count+=n;
        }
        cJSON *o=cJSON_Parse(body); const char *a=jstr(o,"action");
        bool valid=!strcmp(a,"start") || !strcmp(a,"callback") || !strcmp(a,"select") || !strcmp(a,"disconnect");
        cJSON_Delete(o);
        if (!valid) { wipe_free(body); return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Unknown action"); }
        xSemaphoreTake(lock,portMAX_DELAY);
        bool queued=!status.busy && xQueueSend(jobs,&body,0)==pdTRUE;
        if (queued) status.busy=true;
        xSemaphoreGive(lock);
        if (!queued) { wipe_free(body); httpd_resp_set_status(req,"409 Conflict"); return httpd_resp_sendstr(req,"Bosch operation in progress"); }
        httpd_resp_set_type(req,"application/json"); httpd_resp_set_status(req,"202 Accepted");
        return httpd_resp_sendstr(req,"{\"accepted\":true}");
    }
    cJSON *o=cJSON_CreateObject(); if (!o) return unavailable(req,"Insufficient memory");
    xSemaphoreTake(lock,portMAX_DELAY);
    bool available=status.available && now_s()-status.sampled<=180;
    cJSON_AddStringToObject(o,"state",status.state);
    cJSON_AddStringToObject(o,"error",status.error);
    cJSON_AddBoolToObject(o,"linked",status.linked);
    cJSON_AddBoolToObject(o,"busy",status.busy);
    cJSON_AddBoolToObject(o,"available",available);
    if (available) cJSON_AddNumberToObject(o,"temperature_c",status.temperature); else cJSON_AddNullToObject(o,"temperature_c");
    if (status.sampled) cJSON_AddNumberToObject(o,"age_s",now_s()-status.sampled); else cJSON_AddNullToObject(o,"age_s");
    cJSON_AddStringToObject(o,"device",status.device); cJSON_AddStringToObject(o,"zone",status.zone);
    cJSON *zones=cJSON_AddArrayToObject(o,"zones");
    for (unsigned i=0;zones && i<status.zone_count;i++) cJSON_AddItemToArray(zones,cJSON_CreateString(status.zones[i]));
    cJSON_AddNumberToObject(o,"polls",status.polls); cJSON_AddNumberToObject(o,"refreshes",status.refreshes);
    if (status.auth_url && now_s()<status.auth_deadline) cJSON_AddStringToObject(o,"auth_url",status.auth_url);
    xSemaphoreGive(lock);
    char *json=cJSON_PrintUnformatted(o); cJSON_Delete(o);
    if (!json) return unavailable(req,"Insufficient memory");
    httpd_resp_set_type(req,"application/json"); esp_err_t err=httpd_resp_sendstr(req,json); free(json); return err;
}
void bosch_client_start(httpd_handle_t server) {
    lock=xSemaphoreCreateMutex(); jobs=xQueueCreate(1,sizeof(char *));
    if (lock && jobs) xTaskCreate(task,"bosch",8192,NULL,3,&worker);
    const httpd_uri_t get={.uri="/api/bosch",.method=HTTP_GET,.handler=handler};
    const httpd_uri_t post={.uri="/api/bosch",.method=HTTP_POST,.handler=handler};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&get));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server,&post));
}
