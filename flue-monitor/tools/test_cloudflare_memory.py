"""Verify the scoped PSRAM allocator's capabilities and failure semantics."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    tmp=Path(directory)
    (tmp/'sdkconfig.h').write_text('#define CONFIG_SPIRAM 1\n')
    (tmp/'esp_heap_caps.h').write_text('''#pragma once
#include <stdlib.h>
#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
static unsigned calls;static int fail;
static void check(unsigned caps){assert(caps==3);calls++;}
static void *heap_caps_malloc(size_t n,unsigned caps){check(caps);return fail?NULL:malloc(n);}
static void *heap_caps_calloc(size_t n,size_t size,unsigned caps){check(caps);return fail?NULL:calloc(n,size);}
static void *heap_caps_realloc(void *p,size_t n,unsigned caps){check(caps);return fail?NULL:realloc(p,n);}
''')
    (tmp/'test.c').write_text('''#include <assert.h>
#include <string.h>
#include "psram_alloc.h"
int main(void){
 char *p=malloc(8);assert(p);strcpy(p,"keep");
 fail=1;assert(!realloc(p,1000));assert(!strcmp(p,"keep"));
 assert(!malloc(16) && !calloc(2,32) && !strdup("token"));
 unsigned before=calls;assert(!calloc(SIZE_MAX,2));assert(calls==before);
 fail=0;char *q=realloc(p,1000);assert(q && !strcmp(q,"keep"));free(q);
 q=strdup("test");assert(q && !strcmp(q,"test"));free(q);
 unsigned char *zero=calloc(4,16);assert(zero);for(int i=0;i<64;i++)assert(!zero[i]);free(zero);
 return 0;
}
''')
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(tmp),'-I'+str(root/'components/esp_cf_tunnel'),str(tmp/'test.c'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
print('PASS: PSRAM-only malloc/calloc/realloc/strdup, no fallback on exhaustion, overflow and realloc data retention')
