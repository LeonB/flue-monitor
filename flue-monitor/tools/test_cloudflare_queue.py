"""Exercise the actual bounded GET backlog, without opening device sockets."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "cf_tunnel.h"
struct cft_stream {int id,response;bool proxied,paused;cft_stream_handlers_t h;void *ctx;};
static int active,peak,order[100],served,fail_proxy;
bool cft_stream_proxy_available(cft_stream_t *s){(void)s;return active<4;}
int cft_stream_proxy(cft_stream_t *s,const char *service){
 assert(!strcmp(service,"http://127.0.0.1:80"));
 if(fail_proxy)return -1;
 assert(active<4);active++;if(active>peak)peak=active;
 s->proxied=true;order[served++]=s->id;return 0;
}
int cft_stream_respond(cft_stream_t *s,int status,const char *type,const void *body,size_t len){
 (void)type;assert(strlen(body)==len);s->response=status;return 0;
}
void cft_stream_set_handlers(cft_stream_t *s,const cft_stream_handlers_t *h,void *ctx){s->h=*h;s->ctx=ctx;}
void cft_stream_pause_body(cft_stream_t *s,bool pause){s->paused=pause;}
#include "cloudflare_queue.h"
static void close_pending(void){
 for(size_t i=0;i<CLOUDFLARE_PENDING_GETS;i++){
  cft_stream_t *s=pending_gets[i].stream;
  if(s)s->h.on_close(s,s->ctx,false);
 }
 assert(!pending_oldest());reset_gets();
}
int main(void){
 cft_stream_t streams[32]={0};
 // A cold dashboard burst queues instead of returning 503, preserving FIFO.
 for(int i=0;i<14;i++){streams[i].id=i;queue_get(&streams[i],100);assert(!streams[i].response);}
 assert(active==4 && served==4 && pending_oldest());
 while(pending_oldest()){active=0;pump_gets(200);}
 assert(served==14 && peak==4);
 for(int i=0;i<14;i++){assert(streams[i].proxied && !streams[i].paused && order[i]==i);}
 close_pending();memset(streams,0,sizeof streams);active=4;
 // Cancellation frees its entry; a stale close cannot clear a reused slot.
 queue_get(&streams[0],100);void *ctx=streams[0].ctx;void (*closed)(cft_stream_t *,void *,bool)=streams[0].h.on_close;
 closed(&streams[0],ctx,false);queue_get(&streams[1],100);closed(&streams[0],ctx,false);
 assert(pending_oldest()->stream==&streams[1]);close_pending();
 // The backlog has a hard bound and a deadline; neither consumes an origin slot.
 memset(streams,0,sizeof streams);
 for(int i=0;i<CLOUDFLARE_PENDING_GETS;i++)queue_get(&streams[i],100);
 queue_get(&streams[16],100);assert(streams[16].response==503 && active==4);
 pump_gets(100+CLOUDFLARE_QUEUE_TIMEOUT_US-1);assert(!streams[0].response);
 pump_gets(100+CLOUDFLARE_QUEUE_TIMEOUT_US);assert(!pending_oldest());
 for(int i=0;i<CLOUDFLARE_PENDING_GETS;i++)assert(streams[i].response==503 && !streams[i].paused && !streams[i].h.on_close);
 // A queued GET with a body is rejected and detached before its slot is reused.
 memset(streams,0,sizeof streams);queue_get(&streams[0],100);
 streams[0].h.on_body(&streams[0],streams[0].ctx,(const uint8_t *)"x",1);
 assert(streams[0].response==400 && !pending_oldest() && !streams[0].paused && !streams[0].h.on_close);
 queue_get(&streams[1],100);fail_proxy=1;active=0;pump_gets(200);
 assert(streams[1].response==502 && !pending_oldest());fail_proxy=0;
 active=4;queue_get(&streams[2],100);close_pending();
 assert(!pending_oldest() && !pending_ticket);
 puts("PASS 14-request cold burst, four origins, FIFO, cancellation/reuse, queue cap, timeout, body rejection, proxy failure and teardown");
}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);(p/'test.c').write_text(source)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I'+str(root/'main'),'-I'+str(root/'components/esp_cf_tunnel/include'),
                    str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True,timeout=20)
