"""Exercise IDF's real header serializer with the firmware TX-size expression."""
from pathlib import Path
import re, subprocess, tempfile
root = Path(__file__).resolve().parents[1]
sdk = Path.home() / 'Library/Caches/esphome/idf/frameworks/6.0.3'
src = (sdk / 'components/esp_http_client/lib/http_header.c').read_text()
func = src[src.index('int http_header_generate_string('):]
func = func[:func.index('\n}')+2]
firmware = (root / 'main/bosch_client.c').read_text()
expr = re.search(r'\.buffer_size_tx=(.*?)\};', firmware, re.S).group(1)
code = '''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/queue.h>
#define ESP_LOGE(...) ((void)0)
typedef struct item { char *key,*value; STAILQ_ENTRY(item) next; } *http_header_item_handle_t;
STAILQ_HEAD(headers,item);
typedef struct headers *http_header_handle_t;
''' + func + '''
int main(void) {
 for (int length=600; length<=8192; length+=379) {
  char *access_token=malloc(length+1);memset(access_token,'x',length);access_token[length]=0;
  bool authorized=true;
  int capacity=EXPRESSION;
  char *bearer=malloc(length+8);snprintf(bearer,length+8,"Bearer %s",access_token);
  struct headers headers;STAILQ_INIT(&headers);
  struct item item={.key="Authorization",.value=bearer};STAILQ_INSERT_TAIL(&headers,&item,next);
  char *buffer=calloc(capacity,1);int n=512;
  assert(http_header_generate_string(&headers,0,buffer,&n)==0 && n==0);
  n=capacity;assert(http_header_generate_string(&headers,0,buffer,&n)==1);
  assert(strstr(buffer,bearer));free(buffer);free(bearer);free(access_token);
 }
 puts("PASS actual IDF serializer: default 512-byte buffer fails, firmware buffer carries long OAuth headers");
}
'''.replace('EXPRESSION',expr)
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
