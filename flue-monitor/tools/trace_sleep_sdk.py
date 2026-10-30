"""Generate a temporary, guarded sleep_modes.c trace without editing ESP-IDF."""
from pathlib import Path
import sys

source, output = map(Path, sys.argv[1:])
text = source.read_text()
anchor = '#include "esp_private/sleep_event.h"'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '\nextern void flue_sleep_trace_mark(uint32_t stage);')

def surround(body, statement, stage):
    assert body.count(statement) == 1, (stage, statement, body.count(statement))
    return body.replace(statement, f'flue_sleep_trace_mark({stage});\n    {statement}\n    flue_sleep_trace_mark({stage + 1});')

start = text.index('static esp_err_t SLEEP_FN_ATTR esp_sleep_start(')
end = text.index('static uint32_t FORCE_IRAM_ATTR call_rtc_sleep_start(', start)
body = text[start:end]
for stage, statement in [
    (30, 'rtc_clk_cpu_freq_get_config(&cpu_freq_config);'),
    (32, 'rtc_clk_cpu_freq_set_xtal_for_sleep();'),
    (34, 'misc_modules_sleep_prepare(sleep_flags, deep_sleep);'),
    (36, 'rtc_sleep_init(config);'),
    (38, 'rtc_sleep_low_init(s_config.rtc_clk_cal_period, deep_sleep);'),
    (40, 'rtc_clk_cpu_freq_set_config(&cpu_freq_config);'),
    (42, 'misc_modules_wake_prepare(sleep_flags);'),
    (44, 'esp_clk_utils_mspi_speed_mode_sync_after_cpu_freq_switching(cpu_freq_config.source_freq_mhz, cpu_freq_config.freq_mhz);'),
    (46, 'resume_uarts();'),
]:
    body = surround(body, statement, stage)
text = text[:start] + body + text[end:]

start = text.index('esp_err_t esp_light_sleep_start(void)')
body = text[start:]
for stage, statement in [
    (10, 'esp_ipc_isr_stall_other_cpu();'),
    (12, 'esp_ipc_isr_stall_pause();'),
    (14, 'sleep_low_power_clock_calibration(false);'),
    (16, 'periph_inform_out_light_sleep_overhead(s_config.sleep_time_adjustment - sleep_time_overhead_in);'),
    (18, 'err = esp_light_sleep_inner(sleep_flags, clk_flags, flash_enable_time_us);'),
    (50, 'uint64_t rtc_ticks_at_end = rtc_time_get();'),
    (52, 'esp_timer_private_set(high_res_time_at_start + rtc_time_diff);'),
    (54, 'esp_set_time_from_rtc();'),
    (56, 'esp_clk_private_unlock();'),
    (58, 'esp_timer_private_unlock();'),
    (60, 'esp_ipc_isr_stall_resume();'),
    (62, 'esp_ipc_isr_release_other_cpu();'),
    (64, 'wdt_hal_disable(&rtc_wdt_ctx);'),
]:
    body = surround(body, statement, stage)
output.write_text(text[:start] + body)
