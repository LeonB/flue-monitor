"""Execute panel math, settings validation and the actual render branches on host."""
import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
idf = Path(json.loads((root / 'build/project_description.json').read_text())['idf_path'])
cjson = idf / 'components/json/cJSON'
poll = (root / 'main/flue_poll.c').read_text()
parse = poll[poll.index('static bool parse_zone_color('):poll.index('static bool fetch_and_apply_settings(')]
led = (root / 'main/led_display.c').read_text()
state = led[led.index('static bool s_panel_srgb;'):led.index('typedef struct {')]
setters = led[led.index('void led_display_set_panel_correction('):]
render = led[led.index('    if (preview) {'):led.index('    if (led_strip_refresh')]
preamble = r'''
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "cJSON.h"
#include "panel_color.h"
static int64_t clock_us;
static int64_t esp_timer_get_time(void){return clock_us;}
#define portENTER_CRITICAL(x) ((void)0)
#define portEXIT_CRITICAL(x) ((void)0)
#define LED_COUNT 64
static int s_strip;
static uint8_t output[3];
static void led_strip_set_pixel(int s,int i,uint8_t r,uint8_t g,uint8_t b){(void)s;(void)i;output[0]=r;output[1]=g;output[2]=b;}
typedef struct {uint8_t r,g,b;} rgb_t;
static int temperature_to_zone(float t,float c,float h){return t<=c?0:t<=h?1:2;}
static rgb_t trend_neighbor_color(float t,float r,float c,float h,const rgb_t colors[3]){int z=temperature_to_zone(t,c,h);return colors[r>0?z<2?z+1:z:r<0?z>0?z-1:z:z];}
static uint8_t scaled_channel(uint8_t t,uint8_t p,float f,float b,bool s,float g,float gamma){return panel_color_channel(t+(p-t)*f,b,s,g,gamma);}
'''
wrapper = r'''
static void render_snapshot(bool valid) {
 bool preview=s_panel_preview.expires_us>clock_us;
 bool panel_srgb=preview?s_panel_preview.srgb:s_panel_srgb;
 float panel_gamma=preview?s_panel_preview.gamma:s_panel_gamma;
 float *gains=preview?s_panel_preview.gains:s_panel_gains;
 uint32_t preview_color=s_panel_preview.color,preview_brightness=s_panel_preview.brightness;
 float temperature_c=100,zone_cold_max_c=150,zone_optimal_max_c=280,rate_c_per_min=0;
 float envelope=0.5f,color_transition_exponent=3,brightness=96;
 rgb_t colors[3]={{243,181,74},{255,0,0},{0,0,255}};
'''
tests = r'''
static bool apply(const char *text){cJSON *j=cJSON_Parse(text);assert(j);bool ok=apply_panel_settings(j);cJSON_Delete(j);return ok;}
int main(void){
 assert(panel_color_channel(255,255,true,1,2.8f)==255);
 assert(panel_color_channel(0,255,true,1,2.8f)==0);
 assert(panel_color_channel(128,255,true,1,2.8f)==55);
 assert(panel_color_channel(128,255,false,1,2.8f)==37);
 assert(panel_color_channel(128,255,false,1,1)==128);
 assert(panel_color_channel(128,255,false,1,4)==16);
 assert(panel_color_channel(128,255,true,1,1)==panel_color_channel(128,255,true,1,4));
 assert(!apply("{\"panel_gamma\":0}"));assert(!apply("{\"panel_gamma\":4.1}"));
 assert(apply("{\"panel_gamma\":1.5}"));assert(s_panel_gamma==1.5f);
 assert(apply("{}"));assert(s_panel_gamma==2.8f);assert(!s_panel_srgb && s_panel_gains[0]==1);
 assert(apply("{\"panel_srgb\":true,\"panel_red_gain\":0.8,\"panel_green_gain\":1,\"panel_blue_gain\":0.9,\"panel_preview\":{\"active\":true,\"remaining_ms\":500,\"color\":\"#ff0000\",\"brightness\":96,\"srgb\":true,\"red\":1,\"green\":1,\"blue\":1}}"));
 render_snapshot(true);assert(output[0]==96 && output[1]==0 && output[2]==0);
 // Preview keeps working without a sensor reading, but expires locally.
 clock_us=499000;render_snapshot(false);assert(output[0]==96 && output[1]==0);
 clock_us=500000;render_snapshot(true);assert(output[0]==panel_color_channel(243,96,true,0.8f,2.8f));assert(output[1]>0);
 render_snapshot(false);assert(output[0]==96 && output[1]==96 && output[2]==96);
 int64_t expiry=s_panel_preview.expires_us;
 assert(!apply("{\"panel_preview\":{\"active\":true,\"remaining_ms\":180001}}"));assert(s_panel_preview.expires_us==expiry);
 assert(!apply("{\"panel_red_gain\":0}"));
 assert(!apply("{\"panel_srgb\":\"yes\"}"));
 assert(apply("{\"panel_preview\":{\"active\":false}}"));assert(!s_panel_preview.expires_us);
 assert(apply("{\"panel_preview\":{\"active\":true,\"remaining_ms\":500,\"color\":\"#808080\",\"brightness\":96,\"srgb\":false,\"gamma\":1,\"red\":1,\"green\":1,\"blue\":1}}"));
 render_snapshot(false);assert(output[0]==48 && output[1]==48 && output[2]==48);
 assert(apply("{\"panel_preview\":{\"active\":true,\"remaining_ms\":500,\"color\":\"#808080\",\"brightness\":96,\"srgb\":false,\"gamma\":4,\"red\":1,\"green\":1,\"blue\":1}}"));
 render_snapshot(false);assert(output[0]==6 && output[1]==6 && output[2]==6);
 assert(!apply("{\"panel_preview\":{\"active\":true,\"gamma\":4.1}}"));
 led_display_set_panel_preview(999999,0xffffff,96,true,1,1,1,2.8f);assert(s_panel_preview.expires_us-clock_us==180000000);
 assert(apply("{}"));assert(!s_panel_preview.expires_us);
 puts("PASS actual display preview/render: fixed color, sRGB/legacy, gains, local expiry, fallback, cancel, old sidecar, invalid data and TTL clamp");
}
'''
with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    (tmp / 'test.c').write_text(preamble + state + setters + parse + wrapper + render + '}\n' + tests)
    subprocess.run(['cc','-std=c11','-Wno-deprecated-declarations','-fsanitize=address,undefined','-I',str(cjson),'-I',str(root.parent/'components'),str(tmp/'test.c'),str(cjson/'cJSON.c'),'-o',str(tmp/'test')],check=True)
    subprocess.run([str(tmp/'test')],check=True)
