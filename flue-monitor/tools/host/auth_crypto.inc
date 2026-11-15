#include <time.h>
#include <CommonCrypto/CommonDigest.h>
static time_t wall_now = 1794780000;
static time_t auth_host_time(time_t *out) {if(out)*out=wall_now;return wall_now;}
#define time auth_host_time
static int64_t now;
static unsigned char blob[256];
static size_t blob_size;
static bool fail_hash, fail_nvs, fail_token_hash, fail_nvs_set, fail_nvs_commit;
static unsigned char session_blob[1024], pending_blob[1024];
static size_t session_blob_size, pending_size;
static bool pending_sessions;
static unsigned session_writes;

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
static int psa_hash_compute(int alg,const uint8_t *input,size_t n,uint8_t *output,size_t capacity,size_t *length) {
 assert(alg==PSA_ALG_SHA_256 && capacity>=32);if(fail_token_hash)return ESP_FAIL;
 CC_SHA256(input,(CC_LONG)n,output);*length=32;return PSA_SUCCESS;
}
static int nvs_get_blob(int a,const char *key,void *out,size_t *n) {
 (void)a;bool sessions=!strcmp(key,"sessions_v1");
 const unsigned char *data=sessions?session_blob:blob;size_t size=sessions?session_blob_size:blob_size;
 if(!size||*n<size)return ESP_FAIL;if(out)memcpy(out,data,size);*n=size;return ESP_OK;
}
static int nvs_set_blob(int a,const char *key,const void *out,size_t n) {
 (void)a;if(fail_nvs_set)return ESP_FAIL;assert(n<=sizeof pending_blob);
 memcpy(pending_blob,out,n);pending_size=n;pending_sessions=!strcmp(key,"sessions_v1");return ESP_OK;
}
static int nvs_commit(int a) {
 (void)a;if(fail_nvs_commit)return ESP_FAIL;
 if(pending_sessions){memcpy(session_blob,pending_blob,pending_size);session_blob_size=pending_size;session_writes++;}
 else {assert(pending_size<=sizeof blob);memcpy(blob,pending_blob,pending_size);blob_size=pending_size;}
 pending_size=0;return ESP_OK;
}
static void nvs_close(int a) {(void)a;pending_size=0;}
