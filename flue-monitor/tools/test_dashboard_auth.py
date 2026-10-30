"""Run actual firmware authentication code with host HTTP/NVS/clock shims.

macOS CommonCrypto supplies real PBKDF2-HMAC-SHA256 for the crypto shim.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = re.sub(r'^#include .*$','', (root/'main/dashboard_auth.c').read_text(), flags=re.M)
source = source.replace('getpeername(', 'fake_getpeername(')
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
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define MBEDTLS_MD_SHA256 1
typedef int nvs_handle_t;
typedef struct {int fd;const char *cookie,*host,*origin;const char *set_cookie;} httpd_req_t;
bool dashboard_auth_is_remote(httpd_req_t *req);
static int64_t now;
static unsigned char blob[256];
static size_t blob_size;
static bool fail_hash, fail_nvs;
static int64_t esp_timer_get_time(void) {return now;}
static void esp_fill_random(void *out,size_t n) {arc4random_buf(out,n);}
typedef int psa_status_t;
#define PSA_SUCCESS 0
#define PSA_ALG_SHA_256 1
#define PSA_ALG_PBKDF2_HMAC(x) (x)
#define PSA_KEY_DERIVATION_INPUT_COST 1
#define PSA_KEY_DERIVATION_INPUT_SALT 2
#define PSA_KEY_DERIVATION_INPUT_PASSWORD 3
#define PSA_KEY_DERIVATION_OPERATION_INIT {0}
typedef struct {const unsigned char *password,*salt;size_t password_len,salt_len;unsigned rounds;int step;} psa_key_derivation_operation_t;
static int psa_key_derivation_setup(psa_key_derivation_operation_t *o,int alg) {assert(alg==PSA_ALG_SHA_256);o->step=1;return fail_hash?-1:0;}
static int psa_key_derivation_input_integer(psa_key_derivation_operation_t *o,int kind,uint64_t rounds) {assert(kind==PSA_KEY_DERIVATION_INPUT_COST && o->step==1);o->rounds=rounds;o->step=2;return 0;}
static int psa_key_derivation_input_bytes(psa_key_derivation_operation_t *o,int kind,const unsigned char *p,size_t n) {
 if(kind==PSA_KEY_DERIVATION_INPUT_SALT){assert(o->step==2);o->salt=p;o->salt_len=n;o->step=3;}
 else {assert(kind==PSA_KEY_DERIVATION_INPUT_PASSWORD && o->step==3);o->password=p;o->password_len=n;o->step=4;}return 0;
}
static int psa_key_derivation_output_bytes(psa_key_derivation_operation_t *o,unsigned char *out,size_t n) {
 assert(o->step==4);return CCKeyDerivationPBKDF(kCCPBKDF2,(const char *)o->password,o->password_len,o->salt,o->salt_len,kCCPRFHmacAlgSHA256,o->rounds,out,n);
}
static int psa_key_derivation_abort(psa_key_derivation_operation_t *o) {memset(o,0,sizeof(*o));return 0;}
static int nvs_open(const char *a,int b,int *c) {(void)a;(void)b;*c=1;return fail_nvs?ESP_FAIL:ESP_OK;}
static int nvs_get_blob(int a,const char *b,void *out,size_t *n) {(void)a;(void)b;if(!blob_size||*n<blob_size)return ESP_FAIL;memcpy(out,blob,blob_size);*n=blob_size;return ESP_OK;}
static int nvs_set_blob(int a,const char *b,const void *out,size_t n) {(void)a;(void)b;assert(n<=sizeof blob);memcpy(blob,out,n);blob_size=n;return ESP_OK;}
static int nvs_commit(int a) {(void)a;return ESP_OK;}
static void nvs_close(int a) {(void)a;}
static int httpd_req_to_sockfd(httpd_req_t *r) {return r->fd;}
static int fake_getpeername(int fd,struct sockaddr *out,socklen_t *n) {
 if(!fd)return -1;
 if(fd==3 || fd==4){struct sockaddr_in6 *p=(struct sockaddr_in6 *)out;p->sin6_family=AF_INET6;inet_pton(AF_INET6,fd==3?"::ffff:192.168.1.34":"::ffff:127.0.0.1",&p->sin6_addr);*n=sizeof *p;return 0;}
 struct sockaddr_in *p=(struct sockaddr_in *)out;p->sin_family=AF_INET;p->sin_addr.s_addr=htonl(fd==1?0x7f000001:0xc0a80122);*n=sizeof *p;return 0;
}
static int httpd_req_get_hdr_value_str(httpd_req_t *r,const char *key,char *out,size_t n) {
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
 for(size_t i=0;i<AUTH_MAX_SESSIONS;i++)if(s_sessions[i].token[0])return true;
 return false;
}
int main(void) {
 httpd_req_t remote={.fd=1,.host="demo.pagekite.me",.origin="https://demo.pagekite.me"};
 httpd_req_t local={.fd=2,.host="192.168.1.137",.origin="http://192.168.1.137"};
 assert(dashboard_auth_is_remote(&remote) && !dashboard_auth_is_remote(&local));
 remote.host="192.168.1.137";assert(dashboard_auth_is_remote(&remote));remote.host="demo.pagekite.me";
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
 assert(dashboard_auth_check_csrf(&remote));remote.origin="https://demo.pagekite.me.evil";assert(!dashboard_auth_check_csrf(&remote));
 remote.origin="ftp://demo.pagekite.me";assert(!dashboard_auth_check_csrf(&remote));remote.origin="http://demo.pagekite.me";assert(!dashboard_auth_check_csrf(&remote));
 remote.origin=NULL;assert(!dashboard_auth_check_csrf(&remote));assert(dashboard_auth_check_csrf(&local));
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
 assert(strstr(local.set_cookie,"Max-Age=34560000"));
 dashboard_auth_init();assert(!dashboard_auth_check(&local));
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
 assert(strstr(local.set_cookie,"Max-Age=34560000"));
 remote.set_cookie=NULL;assert(dashboard_auth_check(&remote));assert(remote.set_cookie==NULL);
 // Re-login rotates the phone token without consuming another slot or logging out desktop.
 assert(dashboard_auth_login(&remote,"next-password-123",false)==ESP_OK);
 assert(!dashboard_auth_check(&remote));save_cookie(&remote,phone);assert(dashboard_auth_check(&remote));
 assert(dashboard_auth_check(&local));
 dashboard_auth_logout(&remote);assert(!dashboard_auth_check(&remote));assert(dashboard_auth_check(&local));
 // Unknown logout must not clear a valid session.
 remote.cookie="flu_session=invalid";dashboard_auth_logout(&remote);assert(dashboard_auth_check(&local));
 // A password change and restart each revoke every session.
 remote.cookie=NULL;assert(dashboard_auth_login(&remote,"next-password-123",true)==ESP_OK);save_cookie(&remote,phone);remote.cookie=phone;
 assert(dashboard_auth_set_password("next-password-123","final-password-123")==ESP_OK);
 assert(!dashboard_auth_check(&local) && !dashboard_auth_check(&remote));
 assert(dashboard_auth_login(&local,"final-password-123",true)==ESP_OK);save_cookie(&local,desktop);
 remote.cookie=NULL;assert(dashboard_auth_login(&remote,"final-password-123",false)==ESP_OK);save_cookie(&remote,phone);
 dashboard_auth_init();assert(!dashboard_auth_check(&local) && !dashboard_auth_check(&remote));
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
 puts("PASS independent desktop/phone sessions, per-session remember/logout, token rotation, password/restart revocation and bounded LRU eviction");
 puts("PASS password hashing/persistence, crypto/NVS failure, socket-based remote detection, cookie boundaries, browser-session versus persistent cookies, CSRF/HTTPS, lockout, password change and logout");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'auth.c';binary=Path(directory)/'auth'
    path.write_text(preamble+source+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fsanitize-address-use-after-return=always',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
