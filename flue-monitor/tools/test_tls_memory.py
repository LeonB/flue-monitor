"""Exercise the actual TLS hook installation and PSRAM-only allocation policy."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / 'mbedtls').mkdir()
    (tmp / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n')
    (tmp / 'esp_heap_caps.h').write_text('''#pragma once
#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_INTERNAL 2
#define MALLOC_CAP_8BIT 4
void *heap_caps_calloc(size_t,size_t,unsigned);
void *heap_caps_malloc(size_t,unsigned);
''')
    (tmp / 'esp_log.h').write_text('#define ESP_LOGE(...) do { allocation_errors++; } while (0)\nextern int allocation_errors;\n')
    (tmp / 'mbedtls/platform.h').write_text('''#include <stddef.h>
int mbedtls_platform_set_calloc_free(void *(*c)(size_t,size_t),void (*f)(void *));
''')
    (tmp / 'test.c').write_text(r'''
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include "tls_memory.h"
#include "sdkconfig.h"
#include "esp_heap_caps.h"
#include "psram_buffer.h"
static void *(*allocate)(size_t,size_t);
static void (*release)(void *);
static int installs, hook_result, external_available=1, selected;
int allocation_errors;
int mbedtls_platform_set_calloc_free(void *(*c)(size_t,size_t),void (*f)(void *)) {
    installs++;allocate=c;release=f;return hook_result;
}
void *heap_caps_calloc(size_t n,size_t size,unsigned caps) {
    assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    selected=caps;
    if(!external_available || (size && n>SIZE_MAX/size)) return NULL;
    return calloc(n,size);
}
void *heap_caps_malloc(size_t size,unsigned caps) {return heap_caps_calloc(1,size,caps);}
int main(void) {
    void *payload=psram_buffer_alloc(4097);assert(payload);free(payload);
    external_available=0;assert(!psram_buffer_alloc(4097));assert(allocation_errors==1);
    external_available=1;allocation_errors=0;
    assert(tls_memory_init()==ESP_OK);
#if CONFIG_MBEDTLS_CUSTOM_MEM_ALLOC
    assert(installs==1 && allocate && release);
    unsigned char *p=allocate(128,128);assert(p && selected==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    for(size_t i=0;i<16384;i++)assert(p[i]==0);release(p);
    external_available=0;assert(!allocate(1,4096));assert(allocation_errors==1);release(NULL);
    external_available=1;assert(!allocate(SIZE_MAX,2));assert(allocation_errors==2);
    hook_result=-1;assert(tls_memory_init()==ESP_FAIL);
#else
    assert(installs==0 && !allocate && !release);
#endif
    puts("PASS TLS allocator mode, hook errors, PSRAM-only allocation, logged failures and no internal fallback");
}
''')
    for custom in (0, 1):
        (tmp / 'sdkconfig.h').write_text(f'#define CONFIG_MBEDTLS_CUSTOM_MEM_ALLOC {custom}\n')
        binary = tmp / 'test'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-I'+str(tmp),
                        '-I'+str(root / 'main'),
                        '-I'+str(root.parent / 'components/captive_portal/include'),
                        str(tmp / 'test.c'), str(root / 'main/tls_memory.c'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
