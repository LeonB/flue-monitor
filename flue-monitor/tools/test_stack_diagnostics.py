"""Run actual stack registration/sampling/JSON with task shims and real cJSON."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cjson = root / 'managed_components/espressif__cjson/cJSON'
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / 'freertos').mkdir()
    (tmp / 'freertos/FreeRTOS.h').write_text('''#pragma once
#include <stdint.h>
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
void enter(void);void leave(void);
#define portENTER_CRITICAL(p) ((void)(p),enter())
#define portEXIT_CRITICAL(p) ((void)(p),leave())
''')
    (tmp / 'freertos/task.h').write_text('''#pragma once
typedef void *TaskHandle_t;
TaskHandle_t xTaskGetCurrentTaskHandle(void);
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t task);
''')
    code = tmp / 'test.c'
    code.write_text(r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "stack_diagnostics.h"
static int locked, scans;
static uintptr_t self=1;
static unsigned water[STACK_TASK_COUNT+1];
void enter(void){assert(!locked);locked=1;}
void leave(void){assert(locked);locked=0;}
void *xTaskGetCurrentTaskHandle(void){return (void *)self;}
unsigned uxTaskGetStackHighWaterMark(void *task){assert(!locked);scans++;return water[(uintptr_t)task];}
static cJSON *snapshot(void){cJSON *r=cJSON_CreateObject();assert(r);stack_diagnostics_add_json(r);return r;}
static cJSON *task(cJSON *r,const char *name){return cJSON_GetObjectItem(cJSON_GetObjectItem(r,"stacks"),name);}
static int value(cJSON *r,const char *name){return cJSON_GetObjectItem(r,name)->valueint;}
static void *fail_alloc(size_t size){(void)size;return NULL;}
int main(void){
 cJSON *r=snapshot();assert(cJSON_GetArraySize(cJSON_GetObjectItem(r,"stacks"))==0);cJSON_Delete(r);
 stack_diagnostics_sample();assert(!scans);
 stack_diagnostics_register(STACK_MAIN,3584);
 r=snapshot();assert(!task(r,"main"));cJSON_Delete(r);
 water[1]=2048;stack_diagnostics_sample();r=snapshot();
 assert(value(task(r,"main"),"min_free_bytes")==2048);
 assert(value(task(r,"main"),"peak_used_estimate_bytes")==1536);cJSON_Delete(r);
 water[1]=1024;stack_diagnostics_sample();water[1]=1600;stack_diagnostics_sample();
 r=snapshot();assert(value(task(r,"main"),"min_free_bytes")==1024);cJSON_Delete(r);
 water[1]=4000;stack_diagnostics_sample();r=snapshot();
 assert(value(task(r,"main"),"min_free_bytes")==1024);cJSON_Delete(r);
 water[1]=0;stack_diagnostics_sample();r=snapshot();
 assert(value(task(r,"main"),"peak_used_estimate_bytes")==3584);cJSON_Delete(r);
 stack_diagnostics_register((stack_task_t)-1,1024);stack_diagnostics_register(STACK_SENSOR,0);
 for(int i=1;i<STACK_TASK_COUNT;i++){self=i+1;water[self]=512;stack_diagnostics_register((stack_task_t)i,12288);}
 stack_diagnostics_sample();r=snapshot();
 assert(cJSON_GetArraySize(cJSON_GetObjectItem(r,"stacks"))==STACK_TASK_COUNT);
 char *json=cJSON_PrintUnformatted(r);assert(json && strlen(json)+900<2048);free(json);
 cJSON_Hooks hooks={.malloc_fn=fail_alloc,.free_fn=free};cJSON_InitHooks(&hooks);
 stack_diagnostics_add_json(r);cJSON_InitHooks(NULL);cJSON_Delete(r);
 puts("PASS byte units, lifetime minima, absent/unmeasured tasks, zero headroom, bounded scans outside locks, allocation failure and display frame budget");
}
''')
    binary = tmp / 'test'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                    '-fsanitize=address,undefined', '-I'+str(tmp),
                    '-I'+str(root / 'main'), '-I'+str(cjson), str(code),
                    str(root / 'main/stack_diagnostics.c'), str(cjson / 'cJSON.c'),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
