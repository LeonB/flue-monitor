"""Check generated assets; optionally test streaming C fallback using upstream miniz.

python3 tools/test_compressed_assets.py /path/to/miniz-v114.c
The optional reference source implements the same tinfl API as ESP32 ROM.
"""
import gzip
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import generate_web_assets as web

root = Path(__file__).resolve().parents[1]
portal = root.parent / 'components/captive_portal'
assets = list((root / 'main/web_ui').glob('*.js')) + list((root / 'main/web_ui').glob('*.html')) + list((root / 'main/web_ui').glob('*.css')) + list((root / 'main/web_ui/vendor').glob('*.js')) + list((root / 'main/web_ui/vendor').glob('*.css')) + [portal / n for n in ('root.html', 'styles.css', 'alpine.min.js')]
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    subprocess.run([sys.executable, str(root / 'tools/generate_web_assets.py'), str(tmp / 'monitor.h')], check=True)
    subprocess.run([sys.executable, str(portal / 'generate_assets.py'), str(tmp / 'portal_assets_generated.h')], check=True)
    for header in ('monitor.h', 'portal_assets_generated.h'):
        generated = (tmp / header).read_text()
        for array in re.findall(r'unsigned char \w+\[\] = \{([^}]+)\}', generated):
            encoded = bytes(int(n) for n in array.split(',') if n.strip())
            decoded = gzip.decompress(encoded)
            assert encoded[:4] == b'\x1f\x8b\x08\x00'
            assert decoded in list(web.payloads.values()) + [source.read_bytes() for source in assets]
            assert hashlib.sha256(encoded).hexdigest()[:24] in generated
    generated = (tmp / 'monitor.h').read_text()
    assert 'asset_css_gzip[]' not in generated and 'asset_alpine_js_gzip[]' not in generated
    print('PASS: generated gzip payloads, tags, shared CSS and Alpine deduplication')
    if len(sys.argv) < 2:
        sys.exit(0)
    reference = Path(sys.argv[1]).resolve()
    (tmp / 'esp_heap_caps.h').write_text('''#pragma once
#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_INTERNAL 4
void *heap_caps_malloc_prefer(size_t, size_t, ...);
void *heap_caps_calloc_prefer(size_t, size_t, size_t, ...);
''')
    (tmp / 'miniz.h').write_text('#define MINIZ_HEADER_FILE_ONLY\n#include "' + str(reference) + '"\n')
    (tmp / 'esp_http_server.h').write_text('''#pragma once
#include <stddef.h>
#include <stdbool.h>
typedef int esp_err_t;
typedef struct { const char *encoding; int fail; } httpd_req_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define HTTPD_RESP_USE_STRLEN -1
int httpd_req_get_hdr_value_str(httpd_req_t *, const char *, char *, size_t);
int httpd_resp_send_err(httpd_req_t *, int, const char *);
int httpd_resp_set_status(httpd_req_t *, const char *);
int httpd_resp_send(httpd_req_t *, const char *, int);
int httpd_resp_send_chunk(httpd_req_t *, const char *, size_t);
''')
    (tmp / 'harness.c').write_text('''#include "compressed_assets.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "esp_heap_caps.h"
static unsigned preferred_allocations, internal_fallbacks;
void *heap_caps_malloc_prefer(size_t size,size_t count,...) {
 va_list args;va_start(args,count);assert(count==2);
 assert(va_arg(args,int)==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
 assert(va_arg(args,int)==(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));va_end(args);
 preferred_allocations++;
 if(getenv("FAIL_ALLOC"))return NULL;
 if(getenv("NO_PSRAM"))internal_fallbacks++;
 return malloc(size);
}
void *heap_caps_calloc_prefer(size_t count,size_t size,size_t choices,...) {
 assert(choices==2);
 void *p=heap_caps_malloc_prefer(count*size,choices,
   MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
 if(p)memset(p,0,count*size);return p;
}
int httpd_req_get_hdr_value_str(httpd_req_t *r,const char *n,char *v,size_t z) {
 if (!r->encoding || strlen(r->encoding)>=z) return -1; strcpy(v,r->encoding); return 0;
}
int httpd_resp_send_err(httpd_req_t *r,int c,const char *m) { return -1; }
int httpd_resp_set_status(httpd_req_t *r,const char *s) { return 0; }
int httpd_resp_send(httpd_req_t *r,const char *s,int z) { return -1; }
int httpd_resp_send_chunk(httpd_req_t *r,const char *s,size_t z) {
 if(r->fail) return -1;
 return z && fwrite(s,1,z,stdout)!=z ? -1 : 0;
}
int main(int argc,char **argv) {
 httpd_req_t r={0};
 const char *encodings[]={"gzip","br, gzip;q=0","identity","br, gzip;q=0.5",NULL};
 const bool accepted[]={true,false,false,true,false};
 for(int i=0;i<5;i++){r.encoding=encodings[i];assert(compressed_asset_accepts_gzip(&r)==accepted[i]);}
 FILE *f=fopen(argv[1],"rb"); assert(f); fseek(f,0,SEEK_END); size_t n=ftell(f); rewind(f);
 unsigned char *b=malloc(n); assert(fread(b,1,n,f)==n); fclose(f);
 r.fail=argc>3;
 int result=compressed_asset_send_identity(&r,b,n,strtoul(argv[2],NULL,10));free(b);
 if(n>=18)assert(preferred_allocations==2);
 if(getenv("NO_PSRAM"))assert(internal_fallbacks==2);
 return result==0 ? 0 : 1;
}
''')
    executable = tmp / 'decode'
    subprocess.run(['cc', '-w', '-DMINIZ_NO_ARCHIVE_APIS', '-DMINIZ_NO_STDIO', '-DMINIZ_NO_ZLIB_APIS', '-I'+str(tmp), '-I'+str(portal / 'include'), str(portal / 'compressed_assets.c'), str(tmp / 'harness.c'), str(reference), '-o', str(executable)], check=True)
    for source in assets:
        raw = source.read_bytes()
        encoded = tmp / 'input.gz'
        encoded.write_bytes(gzip.compress(raw, mtime=0))
        result = subprocess.run([str(executable), str(encoded), str(len(raw))], capture_output=True)
        assert result.returncode == 0 and result.stdout == raw, source
        import os
        fallback = subprocess.run([str(executable), str(encoded), str(len(raw))], capture_output=True, env={**os.environ, 'NO_PSRAM': '1'})
        assert fallback.returncode == 0 and fallback.stdout == raw, source
        exhausted = subprocess.run([str(executable), str(encoded), str(len(raw))], capture_output=True, env={**os.environ, 'FAIL_ALLOC': '1'})
        assert exhausted.returncode != 0, source
        failure = subprocess.run([str(executable), str(encoded), str(len(raw)), 'disconnect'], capture_output=True)
        assert failure.returncode != 0, source
    encoded.write_bytes(b'bad header')
    assert subprocess.run([str(executable), str(encoded), '1'], capture_output=True).returncode != 0
    print('PASS: actual C fallback, multi-chunk byte equality, encoding negotiation, disconnect and invalid-header handling')
