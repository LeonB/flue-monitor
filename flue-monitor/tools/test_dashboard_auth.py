"""Run actual firmware authentication code with host HTTP/NVS/clock shims.

macOS CommonCrypto supplies real PBKDF2-HMAC-SHA256 for the crypto shim.
"""
from pathlib import Path
from web_test_shim import native_source
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = re.sub(r'^#include .*$','', (root/'main/dashboard_auth.c').read_text(), flags=re.M)
source = native_source(source).replace('getpeername(', 'fake_getpeername(')
preamble = r'''
#define _DARWIN_C_SOURCE
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <arpa/inet.h>
#include <CommonCrypto/CommonKeyDerivation.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 1
#define ESP_ERR_NOT_FOUND 2
#define ESP_ERR_TIMEOUT 3
#define ESP_ERR_INVALID_STATE 4
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define MBEDTLS_MD_SHA256 1
typedef int nvs_handle_t;
typedef struct {int fd;const char *cookie,*host,*origin;const char *set_cookie;} httpd_req_t;
bool dashboard_auth_is_remote(httpd_req_t *req);
''' + (root/'tools/host/auth_crypto.inc').read_text() + 'static int httpd_req_to_sockfd(httpd_req_t *r) {return r->fd;}\n' + (root/'tools/host/auth_peer.inc').read_text() + r'''static int httpd_req_get_hdr_value_str(httpd_req_t *r,const char *key,char *out,size_t n) {
 const char *p=!strcmp(key,"Cookie")?r->cookie:!strcmp(key,"Host")?r->host:r->origin;
 if(!p||strlen(p)>=n)return ESP_FAIL;strcpy(out,p);return ESP_OK;
}
static int httpd_resp_set_hdr(httpd_req_t *r,const char *key,const char *value) {if(!strcmp(key,"Set-Cookie"))r->set_cookie=value;return ESP_OK;}
'''
tests = r'''
static void save_cookie(const httpd_req_t *req, char out[80]) {
 size_t n=strcspn(req->set_cookie,";");assert(n<80);memcpy(out,req->set_cookie,n);out[n]=0;
}
static bool any_session(void) {
 for(size_t i=0;i<AUTH_MAX_SESSIONS;i++)if(session_present(&s_sessions[i]))return true;
 return false;
}
int main(void) {
 httpd_req_t remote={.fd=1,.host="monitor.example.com",.origin="https://monitor.example.com"};
 httpd_req_t local={.fd=2,.host="192.168.1.137",.origin="http://192.168.1.137"};
 assert(dashboard_auth_is_remote(&remote) && !dashboard_auth_is_remote(&local));
 remote.host="192.168.1.137";assert(dashboard_auth_is_remote(&remote));remote.host="monitor.example.com";
 httpd_req_t mapped_local={.fd=3},mapped_remote={.fd=4};assert(!dashboard_auth_is_remote(&mapped_local));assert(dashboard_auth_is_remote(&mapped_remote));
 dashboard_auth_init();assert(!dashboard_auth_is_configured() && !dashboard_auth_check(&remote));
 assert(dashboard_auth_set_password(NULL,"short")==ESP_ERR_INVALID_ARG);
 fail_hash=true;assert(dashboard_auth_set_password(NULL,"test-password-123")==ESP_FAIL);assert(!dashboard_auth_is_configured());fail_hash=false;
 fail_nvs=true;assert(dashboard_auth_set_password(NULL,"test-password-123")==ESP_FAIL);assert(!dashboard_auth_is_configured());fail_nvs=false;
 assert(dashboard_auth_set_password(NULL,"test-password-123")==ESP_OK);assert(dashboard_auth_is_configured());
 assert(blob_size==48 && memmem(blob,blob_size,"test-password-123",17)==NULL);
 s_configured=false;memset(&s_credential,0,sizeof s_credential);dashboard_auth_init();assert(dashboard_auth_is_configured());
 assert(dashboard_auth_login(&remote,"test-password-123",false)==ESP_OK);assert(strstr(remote.set_cookie,"HttpOnly") && strstr(remote.set_cookie,"SameSite=Strict") && strstr(remote.set_cookie,"Secure"));
 char valid[80];save_cookie(&remote,valid);remote.cookie=valid;assert(dashboard_auth_check(&remote));
 char forged[128];snprintf(forged,sizeof forged,"x%s",valid);remote.cookie=forged;assert(!dashboard_auth_check(&remote));
 snprintf(forged,sizeof forged,"%sx",valid);remote.cookie=forged;assert(!dashboard_auth_check(&remote));
 snprintf(forged,sizeof forged,"other=abc; %s; extra=1",valid);remote.cookie=forged;assert(dashboard_auth_check(&remote));
 assert(dashboard_auth_check_csrf(&remote));remote.origin="https://monitor.example.com.evil";assert(!dashboard_auth_check_csrf(&remote));
 remote.origin="ftp://monitor.example.com";assert(!dashboard_auth_check_csrf(&remote));remote.origin="http://monitor.example.com";assert(!dashboard_auth_check_csrf(&remote));
 remote.origin=NULL;assert(!dashboard_auth_check_csrf(&remote));assert(dashboard_auth_check_csrf(&local));
 // The configured public hostname may be 127 characters long.
 const char *saved_host=remote.host;char long_host[128],long_origin[160];
 memset(long_host,'a',127);long_host[127]=0;long_host[63]='.';long_host[124]='.';long_host[125]='n';long_host[126]='l';
 snprintf(long_origin,sizeof long_origin,"https://%s",long_host);remote.host=long_host;remote.origin=long_origin;
 assert(dashboard_auth_check_csrf(&remote));remote.host=saved_host;remote.origin=NULL;
 now=86400LL*1000000;assert(dashboard_auth_check(&remote));remote.cookie=NULL;assert(!dashboard_auth_check(&remote));remote.cookie=valid;now=0;
 for(int i=0;i<5;i++)assert(dashboard_auth_login(&remote,"incorrect-password",false)==ESP_ERR_NOT_FOUND);
 assert(dashboard_auth_login(&remote,"test-password-123",false)==ESP_ERR_TIMEOUT);now+=30000001;
 assert(dashboard_auth_login(&remote,"test-password-123",false)==ESP_OK);
 fail_hash=true;assert(dashboard_auth_login(&remote,"test-password-123",false)==ESP_ERR_NOT_FOUND);fail_hash=false;
 assert(dashboard_auth_set_password("incorrect-password","next-password-123")==ESP_ERR_NOT_FOUND);
 assert(dashboard_auth_set_password("test-password-123","next-password-123")==ESP_OK);assert(!any_session());
 assert(dashboard_auth_login(&local,"test-password-123",false)==ESP_ERR_NOT_FOUND);
 assert(dashboard_auth_login(&local,"next-password-123",false)==ESP_OK);assert(!strstr(local.set_cookie,"Secure"));
 char remembered[80];
 assert(dashboard_auth_login(&local,"next-password-123",true)==ESP_OK);
 save_cookie(&local,remembered);local.cookie=remembered;
 now=1000LL*86400*1000000;assert(dashboard_auth_check(&local));
 assert(strstr(local.set_cookie,"Max-Age=7776000"));
 dashboard_auth_init();assert(dashboard_auth_check(&local));
 assert(dashboard_auth_login(&local,"next-password-123",true)==ESP_OK);save_cookie(&local,remembered);
 assert(dashboard_auth_set_password("next-password-123","final-password-123")==ESP_OK);assert(!dashboard_auth_check(&local));
 assert(dashboard_auth_set_password("final-password-123","next-password-123")==ESP_OK);
 dashboard_auth_logout(&local);assert(!dashboard_auth_check(&local));now=0;
 assert(dashboard_auth_login(&local,"next-password-123",false)==ESP_OK);
 assert(!strstr(local.set_cookie,"Max-Age") && !strstr(local.set_cookie,"Expires"));
 now=86400LL*1000000;save_cookie(&local,remembered);local.cookie=remembered;assert(dashboard_auth_check(&local));
 now+=86400LL*1000000;assert(dashboard_auth_check(&local));
 local.cookie=NULL;assert(!dashboard_auth_check(&local));
 dashboard_auth_init();local.cookie=remembered;assert(!dashboard_auth_check(&local));now=0;
 dashboard_auth_logout(&local);assert(!any_session() && strstr(local.set_cookie,"Max-Age=0"));
 // Independent desktop and phone sessions, including different remember flags.
 local.cookie=NULL;remote.cookie=NULL;now=0;
 assert(dashboard_auth_login(&local,"next-password-123",true)==ESP_OK);
 char desktop[80],phone[80];save_cookie(&local,desktop);local.cookie=desktop;
 assert(dashboard_auth_login(&remote,"next-password-123",false)==ESP_OK);
 save_cookie(&remote,phone);remote.cookie=phone;
 assert(strcmp(desktop,phone));assert(dashboard_auth_check(&local));
 assert(!strcmp(local.cookie,desktop)); // Validation never refreshes the cookie.

 remote.set_cookie=NULL;assert(dashboard_auth_check(&remote));assert(remote.set_cookie==NULL);
 // Re-login rotates the phone token without consuming another slot or logging out desktop.
 assert(dashboard_auth_login(&remote,"next-password-123",false)==ESP_OK);
 assert(!dashboard_auth_check(&remote));save_cookie(&remote,phone);assert(dashboard_auth_check(&remote));
 assert(dashboard_auth_check(&local));
 dashboard_auth_logout(&remote);assert(!dashboard_auth_check(&remote));assert(dashboard_auth_check(&local));
 // Unknown logout must not clear a valid session.
 remote.cookie="flu_session=invalid";dashboard_auth_logout(&remote);assert(dashboard_auth_check(&local));
 // A password change revokes all sessions; restart preserves only remembered ones.
 remote.cookie=NULL;assert(dashboard_auth_login(&remote,"next-password-123",true)==ESP_OK);save_cookie(&remote,phone);remote.cookie=phone;
 assert(dashboard_auth_set_password("next-password-123","final-password-123")==ESP_OK);
 assert(!dashboard_auth_check(&local) && !dashboard_auth_check(&remote));
 assert(dashboard_auth_login(&local,"final-password-123",true)==ESP_OK);save_cookie(&local,desktop);
 remote.cookie=NULL;assert(dashboard_auth_login(&remote,"final-password-123",false)==ESP_OK);save_cookie(&remote,phone);
 dashboard_auth_init();assert(dashboard_auth_check(&local) && !dashboard_auth_check(&remote));
 assert(dashboard_auth_logout(&local)==ESP_OK);
 // Bounded capacity evicts only the least recently used session.
 char cookies[AUTH_MAX_SESSIONS+1][80];
 for(size_t i=0;i<AUTH_MAX_SESSIONS;i++) {
  now+=(int64_t)1000000;local.cookie=NULL;
  assert(dashboard_auth_login(&local,"final-password-123",false)==ESP_OK);save_cookie(&local,cookies[i]);
 }
 now+=1000000;local.cookie=cookies[0];assert(dashboard_auth_check(&local));
 now+=1000000;local.cookie=NULL;assert(dashboard_auth_login(&local,"final-password-123",false)==ESP_OK);save_cookie(&local,cookies[AUTH_MAX_SESSIONS]);
 for(size_t i=0;i<=AUTH_MAX_SESSIONS;i++){local.cookie=cookies[i];assert(dashboard_auth_check(&local)==(i!=1));}
 // Re-login at full capacity must not evict another browser.
 local.cookie=cookies[0];assert(dashboard_auth_login(&local,"final-password-123",true)==ESP_OK);save_cookie(&local,cookies[0]);
 for(size_t i=0;i<=AUTH_MAX_SESSIONS;i++){local.cookie=cookies[i];assert(dashboard_auth_check(&local)==(i!=1));}
 // Only hashes, not raw browser cookies, reach durable storage.
 assert(session_blob_size==sizeof(saved_sessions_t)&&session_blob_size<1024);
 assert(memmem(session_blob,session_blob_size,cookies[0]+12,64)==NULL);
 // Ordinary authenticated requests neither renew the cookie nor write NVS.
 unsigned saved_writes=session_writes;local.cookie=cookies[0];local.set_cookie=NULL;
 for(int i=0;i<100;i++)assert(dashboard_auth_check(&local));
 assert(session_writes==saved_writes&&local.set_cookie==NULL);
 // The same cookie works after a restart, but expires after a fixed90days.
 dashboard_auth_init();assert(dashboard_auth_check(&local));
 time_t issued=wall_now;wall_now+=AUTH_COOKIE_SECONDS-1;assert(dashboard_auth_check(&local));
 wall_now++;assert(!dashboard_auth_check(&local));dashboard_auth_init();assert(!dashboard_auth_check(&local));
 wall_now=issued;
 // Boot before clock sync fails closed, without destroying the stored token.
 wall_now=0;dashboard_auth_init();assert(!dashboard_auth_check(&local));
 assert(dashboard_auth_login(&local,"final-password-123",true)==ESP_ERR_INVALID_STATE);
 wall_now=issued;assert(dashboard_auth_check(&local));
 // A failed persistent mutation must not report success or issue a cookie.
 char active[80];memcpy(active,cookies[0],sizeof active);local.cookie=active;
 for(int failure=0;failure<3;failure++) {
  fail_nvs=failure==0;fail_nvs_set=failure==1;fail_nvs_commit=failure==2;
  local.set_cookie=NULL;
  assert(dashboard_auth_login(&local,"final-password-123",true)!=ESP_OK);
  assert(local.set_cookie==NULL&&dashboard_auth_check(&local));
  assert(dashboard_auth_logout(&local)!=ESP_OK&&dashboard_auth_check(&local));
  fail_nvs=fail_nvs_set=fail_nvs_commit=false;
  dashboard_auth_init();assert(dashboard_auth_check(&local));
 }
 assert(dashboard_auth_logout(&local)==ESP_OK);dashboard_auth_init();assert(!dashboard_auth_check(&local));
 // Re-login from remembered to transient removes the durable token too.
 local.cookie=NULL;assert(dashboard_auth_login(&local,"final-password-123",true)==ESP_OK);save_cookie(&local,active);local.cookie=active;
 assert(dashboard_auth_login(&local,"final-password-123",false)==ESP_OK);save_cookie(&local,active);
 assert(dashboard_auth_check(&local));dashboard_auth_init();assert(!dashboard_auth_check(&local));
 // A password change invalidates even a snapshot left on disk at power loss.
 local.cookie=NULL;assert(dashboard_auth_login(&local,"final-password-123",true)==ESP_OK);save_cookie(&local,active);local.cookie=active;
 assert(dashboard_auth_set_password("final-password-123","another-password")==ESP_OK);
 dashboard_auth_init();assert(!dashboard_auth_check(&local));
 // Corruption/version mismatch is never accepted as a valid session store.
 local.cookie=NULL;assert(dashboard_auth_login(&local,"another-password",true)==ESP_OK);save_cookie(&local,active);local.cookie=active;
 session_blob_size--;dashboard_auth_init();assert(!dashboard_auth_check(&local));
 session_blob_size++;session_blob[0]=99;dashboard_auth_init();assert(!dashboard_auth_check(&local));
 // Token hash failure cannot create a session or accept an existing cookie.
 fail_token_hash=true;assert(dashboard_auth_login(&local,"another-password",true)==ESP_FAIL);assert(!dashboard_auth_check(&local));fail_token_hash=false;
 // All eight remembered slots persist at fixed size. A ninth replaces one.
 assert(dashboard_auth_set_password("another-password","bounded-password")==ESP_OK);
 char durable[AUTH_MAX_SESSIONS+1][80];
 for(size_t i=0;i<AUTH_MAX_SESSIONS;i++) {
  local.cookie=NULL;now+=1000000;
  assert(dashboard_auth_login(&local,"bounded-password",true)==ESP_OK);save_cookie(&local,durable[i]);
  assert(session_blob_size==sizeof(saved_sessions_t));
 }
 dashboard_auth_init();
 for(size_t i=0;i<AUTH_MAX_SESSIONS;i++){local.cookie=durable[i];assert(dashboard_auth_check(&local));}
 now+=1000000;local.cookie=durable[0];assert(dashboard_auth_check(&local));
 local.cookie=NULL;now+=1000000;
 assert(dashboard_auth_login(&local,"bounded-password",true)==ESP_OK);save_cookie(&local,durable[AUTH_MAX_SESSIONS]);
 dashboard_auth_init();
 for(size_t i=0;i<=AUTH_MAX_SESSIONS;i++){local.cookie=durable[i];assert(dashboard_auth_check(&local)==(i!=1));}
 puts("PASS persistent hashed sessions, fixed expiry, reboot, clock sync, durable logout/rotation/password revocation, corruption, NVS failure and zero per-request writes");
 puts("PASS independent desktop/phone sessions, per-session remember/logout, token rotation, password revocation and remembered restart survival and bounded LRU eviction");
 puts("PASS password hashing/persistence, crypto/NVS failure, socket-based remote detection, cookie boundaries, browser-session versus persistent cookies, CSRF/HTTPS, lockout, password change and logout");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'auth.c';binary=Path(directory)/'auth'
    path.write_text(preamble+source+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fsanitize-address-use-after-return=always',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
