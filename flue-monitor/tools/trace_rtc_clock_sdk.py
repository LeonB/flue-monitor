"""Trace only the CPU-clock restore path; preserve rtc_clk.c's linker name."""
from pathlib import Path
import sys

source, output = map(Path, sys.argv[1:])
text = source.read_text()
anchor = '#include "sdkconfig.h"'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '\nextern void flue_sleep_clock_trace_mark(uint32_t stage);')

def surround(body, statement, stage):
    assert body.count(statement) == 1, (stage, statement, body.count(statement))
    return body.replace(statement, f'flue_sleep_clock_trace_mark({stage});\n    {statement}\n    flue_sleep_clock_trace_mark({stage + 1});')

start = text.index('void rtc_clk_cpu_freq_set_config(')
end = text.index('\nvoid rtc_clk_cpu_freq_get_config(', start)
body = text[start:end]
for stage, statement in [
    (100, 'soc_xtal_freq_t xtal_freq = rtc_clk_xtal_freq_get();'),
    (102, 'soc_cpu_clk_src_t old_cpu_clk_src = clk_ll_cpu_get_src();'),
    (104, 'rtc_clk_cpu_freq_to_xtal(xtal_freq, 1);'),
    (108, 'rtc_clk_bbpll_disable();'),
    (110, 'rtc_clk_bbpll_enable();'),
    (114, 'rtc_clk_bbpll_configure(rtc_clk_xtal_freq_get(), config->source_freq_mhz);'),
    (116, 'rtc_clk_cpu_freq_to_pll_mhz(config->freq_mhz);'),
]:
    body = surround(body, statement, stage)
statement = 'rtc_clk_wait_for_slow_cycle();'
assert body.count(statement) == 2
body = body.replace(statement, f'flue_sleep_clock_trace_mark(106); {statement} flue_sleep_clock_trace_mark(107);', 1)
pos = body.rindex(statement)
body = body[:pos] + 'flue_sleep_clock_trace_mark(112); ' + body[pos:pos + len(statement)] + ' flue_sleep_clock_trace_mark(113);' + body[pos + len(statement):]
text = text[:start] + body + text[end:]

start = text.index('NOINLINE_ATTR static void rtc_clk_cpu_freq_to_pll_mhz(')
end = text.index('\nvoid rtc_clk_cpu_freq_set_xtal(', start)
body = text[start:end]
for stage, statement in [
    (120, 'clk_ll_cpu_set_freq_mhz_from_pll(cpu_freq_mhz);'),
    (122, 'clk_ll_cpu_set_src(SOC_CPU_CLK_SRC_PLL);'),
    (124, 'esp_rom_set_cpu_ticks_per_us(cpu_freq_mhz);'),
    (126, 'rtc_clk_wait_for_slow_cycle();'),
    (128, 'esp_rom_delay_us(30);'),
]:
    body = surround(body, statement, stage)
text = text[:start] + body + text[end:]
output.write_text(text)
