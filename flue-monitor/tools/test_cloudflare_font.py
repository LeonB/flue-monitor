"""Exercise the direct public-font streamer, including bounded backpressure."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cf_tunnel.h"
static bool fail_alloc;
static unsigned allocations;
static void *buffer_memory_alloc(size_t n) {if(fail_alloc)return NULL;allocations++;return malloc(n);}
struct cft_stream {int status;size_t bytes,buffered,peak;bool ended,reset,fail_write,fail_headers;const char *condition;char cache[64];cft_stream_handlers_t handlers;void *ctx;unsigned char output[8192];};
const char *cft_stream_header(const cft_stream_t *s,const char *key){assert(!strcmp(key,"if-none-match"));return s->condition;}
size_t cft_stream_buffered(const cft_stream_t *s){return s->buffered;}
void cft_stream_set_handlers(cft_stream_t *s,const cft_stream_handlers_t *h,void *ctx){s->handlers=*h;s->ctx=ctx;}
int cft_stream_send_headers(cft_stream_t *s,int code,const cft_header_t *h,size_t n){s->status=code;for(size_t i=0;i<n;i++)if(!strcmp(h[i].name,"cache-control"))strcpy(s->cache,h[i].value);return s->fail_headers?-1:0;}
int cft_stream_write(cft_stream_t *s,const void *p,size_t n){if(s->fail_write)return -1;assert(n<=512);memcpy(s->output+s->bytes,p,n);s->bytes+=n;s->buffered+=n;if(s->buffered>s->peak)s->peak=s->buffered;return 0;}
int cft_stream_end(cft_stream_t *s){assert(!s->ended);s->ended=true;return 0;}
void cft_stream_reset(cft_stream_t *s){s->reset=true;}
int cft_stream_respond(cft_stream_t *s,int code,const char *t,const void *p,size_t n){(void)t;if(p)assert(strlen(p)==n);s->status=code;return 0;}
#include "font_under_test.h"
static void close_stream(cft_stream_t *s){if(s->handlers.on_close){s->handlers.on_close(s,s->ctx,!s->reset);allocations--;s->ctx=NULL;}}
int main(void){
 static char bytes[5000];for(size_t i=0;i<sizeof bytes;i++)bytes[i]=(char)(i%251);
 const cloudflare_font_t fonts[]={{"/fonts/test.woff2",bytes,bytes+sizeof bytes,"\"0123456789abcdef01234567\""}};
 cft_stream_t s={0};assert(!cloudflare_serve_font(&s,"/dashboard.js",fonts,1));assert(!s.status);
 assert(cloudflare_serve_font(&s,"/fonts/test.woff2?v=0123456789abcdef01234567",fonts,1));assert(s.status==200);assert(strstr(s.cache,"immutable"));assert(s.bytes==512);
 s.handlers.on_writable(&s,s.ctx);assert(s.bytes==512);
 while(!s.ended){s.buffered=0;s.handlers.on_writable(&s,s.ctx);}assert(s.bytes==sizeof bytes && s.peak==512);assert(!memcmp(s.output,bytes,sizeof bytes));close_stream(&s);assert(!allocations);
 s=(cft_stream_t){.condition="*"};cloudflare_serve_font(&s,"/fonts/test.woff2",fonts,1);assert(s.status==304 && s.ended && !allocations);
 s=(cft_stream_t){0};assert(!cloudflare_serve_font(&s,"/fonts/test.woff2?v=wrong",fonts,1));assert(!s.status && !allocations);
 char long_uri[256];memset(long_uri,'x',sizeof long_uri);memcpy(long_uri,"/fonts/test.woff2?",strlen("/fonts/test.woff2?"));long_uri[255]=0;s=(cft_stream_t){0};assert(!cloudflare_serve_font(&s,long_uri,fonts,1));assert(!s.status);
 s=(cft_stream_t){0};cloudflare_serve_font(&s,"/fonts/test.woff2?V=0123456789abcdef01234567",fonts,1);assert(strstr(s.cache,"immutable"));close_stream(&s);
 s=(cft_stream_t){0};fail_alloc=true;cloudflare_serve_font(&s,"/fonts/test.woff2",fonts,1);assert(s.status==503);fail_alloc=false;
 s=(cft_stream_t){.fail_write=true};cloudflare_serve_font(&s,"/fonts/test.woff2",fonts,1);assert(s.reset);close_stream(&s);
 s=(cft_stream_t){.fail_headers=true};cloudflare_serve_font(&s,"/fonts/test.woff2",fonts,1);assert(s.reset);close_stream(&s);
 s=(cft_stream_t){0};cloudflare_serve_font(&s,"/fonts/test.woff2",fonts,1);close_stream(&s);assert(!allocations);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'buffer_memory.h').write_text('#pragma once\n')
 (p/'font_under_test.h').write_text((root/'main/cloudflare_font.h').read_text())
 (p/'test.c').write_text(source)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(p),'-I'+str(root/'components/esp_cf_tunnel/include'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS byte-exact fonts, 512-byte backpressure, cache/version queries, 304, cancellation and allocation/write/header failures')
