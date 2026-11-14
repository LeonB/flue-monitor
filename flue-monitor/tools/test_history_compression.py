"""Exercise the actual history compression and ring reads under sanitizers."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'main/sensors.c').read_text()
header = (root / 'main/sensors.h').read_text().replace('#pragma once', '').replace('#include "esp_err.h"', 'typedef int esp_err_t;')
state = source[source.index('static history_sample_t *s_history;'):source.index('// If a device was left holding the bus')]
state = state.replace('static uint32_t s_history_tick = 0;', '')
reader = source[source.index('size_t sensors_get_history('):]
preamble = r"""
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE 1
#define ESP_ERR_NO_MEM 2
#define buffer_memory_alloc malloc
#define s_last_reading_mutex 0
#define portMAX_DELAY 0
#define xSemaphoreTake(a,b) ((void)0)
#define xSemaphoreGive(a) ((void)0)
"""
tests = r"""
static history_sample_t point(unsigned t,float c,float rate,int zone) {
 return (history_sample_t){t,c,rate,zone};
}
static void reset(void) {s_history_count=0;s_history_head=0;}
int main(void) {
 _Static_assert(sizeof(history_sample_t)==16,"Unchanged sample storage");
 s_history=calloc(SENSORS_HISTORY_CAPACITY,sizeof(*s_history));assert(s_history);
 history_sample_t out[SENSORS_HISTORY_CAPACITY];
 // A year of stable samples retains both ends, not just the first point.
 for(unsigned i=0;i<131400;i++)history_push(point(i*240,20.1f+(i%2)*0.2f,0,1));
 assert(sensors_get_history(out,360)==2);
 assert(out[0].uptime_s==0 && out[1].uptime_s==131399*240);
 assert(out[0].thermocouple_c==20 && out[1].thermocouple_c==20);
 // Keep the plateau end immediately before a rise and the top before a fall.
 history_push(point(31536000,30,1,1));history_push(point(31536240,20,-1,1));
 assert(sensors_get_history(out,360)==4);assert(out[2].thermocouple_c==30);
 // Gradual changes cannot disappear through a rolling tolerance comparison.
 reset();for(unsigned i=0;i<100;i++)history_push(point(i*240,20+i*0.1f,0,1));
 size_t n=sensors_get_history(out,360);assert(n>=20);
 assert(out[0].thermocouple_c==20 && out[n-1].thermocouple_c==30);
 // Zone and rate changes survive even at identical rounded temperature.
 reset();history_push(point(0,20,0,1));history_push(point(240,20,0,1));
 history_push(point(480,20,0,2));assert(s_history_count==3);
 history_push(point(720,20,1,2));assert(s_history_count==4);
 // Rounding boundaries, including temperatures below zero.
 reset();history_push(point(0,20.49f,0,1));history_push(point(240,20.5f,0,1));
 history_push(point(480,-1.5f,0,1));
 assert(sensors_get_history(out,360)==3);
 assert(out[0].thermocouple_c==20 && out[1].thermocouple_c==21 && out[2].thermocouple_c==-2);
 // Replacing a stable tail also works across ring wrap; reads stay ordered.
 reset();for(unsigned i=0;i<1000;i++)history_push(point(i*240,i,0,1));
 assert(sensors_get_history(out,360)==360);assert(out[0].uptime_s==640*240);
 history_push(point(1000*240,999,0,1));history_push(point(1001*240,999,0,1));
 assert(sensors_get_history(out,360)==360);
 assert(out[358].uptime_s==999*240 && out[359].uptime_s==1001*240);
 assert(sensors_get_history(out,1)==1 && out[0].uptime_s==1001*240);
 free(s_history);puts("PASS stable year, endpoints, peaks, drift, zones, rates, rounding and ring wrap");
}
"""
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);c=path/'history.c';exe=path/'history'
 c.write_text(preamble+header+state+reader+tests)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,timeout=20)
