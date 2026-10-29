"""Check generated URL dependencies and execute the real asset response handler."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import generate_web_assets as web

for name, raw in web.payloads.items():
    assert web.versions[name] == hashlib.sha256(raw).hexdigest()[:24]
for name in ("html", "manifest"):
    raw = web.payloads[name].decode()
    for url in re.findall(r"(?:href|src)=[\"']([^\"']+)|[\"]src[\"]: [\"]([^\"]+)", raw):
        target = next(part for part in url if part)
        if target.startswith("/") and target != "/":
            assert target in web.versioned_urls.values(), target
html = web.payloads["html"].decode()
assert "/service-worker.js?v=" not in html
assert html.count('as="font"') == 4
assert "&v=" in html  # launch images retain their size query
# A font update invalidates consumers, but leaves unrelated scripts unchanged.
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    original = dict(web.versions)
    font = tmp / "changed.woff2"
    font.write_bytes(web.payloads["caprasimo_400"] + b"changed")
    web.assets["caprasimo_400"] = font
    web.payloads.clear(); web.versions.clear(); web.versioned_urls.clear()
    for name in web.assets:
        web.prepare(name)
    assert original["html"] != web.versions["html"]
    assert original["js"] == web.versions["js"]

source = (web.root / "main/rest_api.c").read_text()
handler = source.split("static esp_err_t serve_asset(", 1)[1].split("// iOS fetches", 1)[0]
handler = "static esp_err_t serve_asset(" + handler
shim = r'''#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NOT_FOUND -2
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_404_NOT_FOUND 404
struct request { const char *uri; const char *condition; bool gzip; bool denied; int status; char cache[80]; char etag[80]; };
typedef struct request httpd_req_t;
static bool auth_required(httpd_req_t *r) {return r->denied;}
static int httpd_req_get_url_query_str(httpd_req_t *r,char *b,size_t n) {
 const char *p=strchr(r->uri,'?'); if(!p)return ESP_ERR_NOT_FOUND;
 if(strlen(++p)>=n)return ESP_FAIL; strcpy(b,p); return ESP_OK;
}
static int httpd_query_key_value(const char *q,const char *key,char *b,size_t n) {
 size_t z=strlen(key); while(*q) { const char *e=strchr(q,'&');size_t len=e?(size_t)(e-q):strlen(q);
 if(len>z && !strncmp(q,key,z) && q[z]=='=') {size_t v=len-z-1;if(v>=n)return ESP_FAIL;memcpy(b,q+z+1,v);b[v]=0;return ESP_OK;}
 if(!e)break;q=e+1;} return ESP_ERR_NOT_FOUND;
}
static int httpd_req_get_hdr_value_str(httpd_req_t *r,const char *k,char *b,size_t n) {if(!r->condition)return ESP_FAIL;snprintf(b,n,"%s",r->condition);return ESP_OK;}
static int httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v) {if(!strcmp(k,"Cache-Control"))strcpy(r->cache,v);if(!strcmp(k,"ETag"))strcpy(r->etag,v);return 0;}
static int httpd_resp_set_type(httpd_req_t *r,const char *v){return 0;}
static int httpd_resp_set_status(httpd_req_t *r,const char *v){r->status=atoi(v);return 0;}
static int httpd_resp_send_err(httpd_req_t *r,int s,const char *v){r->status=s;return -1;}
static int httpd_resp_send(httpd_req_t *r,const char *v,size_t n){return 0;}
static bool compressed_asset_accepts_gzip(httpd_req_t *r){return r->gzip;}
static int compressed_asset_send_identity(httpd_req_t *r,const unsigned char *v,size_t n,size_t z){return 0;}
'''
test = r'''
static void check(const char *uri,const char *type,bool gzip,const char *condition,int status,const char *cache) {
 httpd_req_t r={.uri=uri,.gzip=gzip,.condition=condition,.status=200};
 serve_asset(&r,type,"body",4,"\"0123456789abcdef01234567\"",(const unsigned char *)"gzip",4,"\"gzip-tag\"");
 assert(r.status==status);assert(!strcmp(r.cache,cache));
 if(status<400)assert(!strcmp(r.etag,gzip?"\"gzip-tag\"":"\"0123456789abcdef01234567\""));
}
int main(void) {
 const char *immutable="private, max-age=31536000, immutable";
 check("/fonts/a.woff2?v=0123456789abcdef01234567","font/woff2",false,NULL,200,immutable);
 check("/dashboard.js?v=0123456789abcdef01234567","application/javascript",true,NULL,200,immutable);
 check("/dashboard.js?v=0123456789abcdef01234567","application/javascript",true,"\"gzip-tag\"",304,immutable);
 check("/startup.png?size=640x1136&v=0123456789abcdef01234567","image/png",true,NULL,200,immutable);
 check("/fonts/a.woff2?v=old","font/woff2",false,NULL,404,"no-store");
 check("/fonts/a.woff2?v=","font/woff2",false,NULL,404,"no-store");
 check("/fonts/a.woff2?v=0123456789abcdef012345670","font/woff2",false,NULL,404,"no-store");
 check("/fonts/a.woff2","font/woff2",false,NULL,200,"no-cache");
 check("/startup.png?size=640x1136","image/png",true,NULL,200,"no-cache");
 check("/service-worker.js?v=old","application/javascript",true,NULL,200,"no-cache");
 check("/?v=old","text/html",true,NULL,200,"no-cache");
 httpd_req_t denied={.uri="/dashboard.js?v=0123456789abcdef01234567",.denied=true};
 assert(serve_asset(&denied,"application/javascript","body",4,"\"0123456789abcdef01234567\"",NULL,0,NULL)==ESP_FAIL);
 puts("PASS actual asset handler: immutable versions, rejected stale hashes, encoding ETags, fixed HTML/worker policy and auth");
}
'''
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / "cache.c").write_text(shim + handler + test)
    subprocess.run(["cc", "-fsanitize=address,undefined", "-g", str(tmp / "cache.c"), "-o", str(tmp / "cache")], check=True)
    subprocess.run([str(tmp / "cache")], check=True)
print("PASS generated content hashes, versioned HTML/manifest, font dependency invalidation and unchanged script reuse")
