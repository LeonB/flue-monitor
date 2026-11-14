"""Local retry investigation: ordinary matrix separate from synthetic readback faults.
No production changes or hardware access. Outputs under .cache/iwdt-retry-progress.
"""
import json
import subprocess
from pathlib import Path
import iwdt_dualcore_model as m

OUT = m.PROJECT / '.cache/iwdt-retry-progress'
OUT.mkdir(exist_ok=True)
original_build = m.build

def instrument(source):
    source = source.replace('static unsigned c_feeds;', 'static unsigned c_feeds; static unsigned tr_feeds, retries, fed_retries, before_feed; static unsigned peak_feeds, peak_retries, peak_fed;')
    source = source.replace('c_feeds++;', 'c_feeds++; if (!strcmp(cur->name, "transition")) tr_feeds++;')
    source = source.replace('c_feeds = 0;', 'c_feeds = 0; tr_feeds = retries = fed_retries = before_feed = 0;')
    assert source.count('unsigned ps = flue_iwdt_mask_high_interrupts();') == 1
    source = source.replace('unsigned ps = flue_iwdt_mask_high_interrupts();', 'before_feed = tr_feeds; unsigned ps = flue_iwdt_mask_high_interrupts();')
    # Only transition has these continue statements in proposal source.
    source = source.replace('            continue;', '            retries++; if (tr_feeds > before_feed) fed_retries++; continue;')
    source = source.replace('counts[r]++;', 'if(tr_feeds>peak_feeds)peak_feeds=tr_feeds; if(retries>peak_retries)peak_retries=retries; if(fed_retries>peak_fed)peak_fed=fed_retries; counts[r]++;')
    source = source.replace('    return 0;\n}', '    fprintf(stderr,"RETRY_METRICS feeds=%u retries=%u fed_retries=%u\\n",peak_feeds,peak_retries,peak_fed); return 0;\n}')
    source = source.replace('if (r == R_OK) fprintf(stderr, "== ok\\n");', 'fprintf(stderr,"PROBE cycles=%llu feeds=%u retries=%u fed_retries=%u\\n",(unsigned long long)cyc,tr_feeds,retries,fed_retries); if (r == R_OK) fprintf(stderr, "== ok\\n");')
    return source

def compile_source(source, path):
    path.write_text(source)
    exe = path.with_suffix('')
    subprocess.run(['cc','-std=c11','-O2','-Wno-deprecated-declarations',str(path),'-o',str(exe)],check=True)
    return exe

def build(variant, settle, outdir, proposal_inc=None):
    exe = original_build(variant,settle,outdir,proposal_inc)
    if variant == 'proposal':
        compile_source(instrument(exe.with_suffix('.c').read_text()),exe.with_suffix('.c'))
    return exe

# Reuse identical existing scenario definitions and expectation checks.
m.build = build
runner = Path(__file__).with_name('run_review.py').read_text()
runner = runner.replace("OUT = Path('/tmp/flue-iwdt-v3-review')", 'OUT = Path('+repr(str(OUT / 'ordinary'))+')')
runner = runner.replace('OUT.mkdir(exist_ok=True)', 'OUT.mkdir(parents=True, exist_ok=True)')
runner = runner.replace('raise SystemExit(any(not r[\'passed\'] for r in results))', 'assert all(r["passed"] for r in results)')
exec(compile(runner,'retry_matrix','exec'),{'__name__':'retry_matrix'})

source = (OUT/'ordinary/proposal_0.c').read_text()
# Persistently wrong WPROTECT readback, while actual protection/feed behavior stays normal.
anchor = 'return WP_OPEN; }'
assert source.count(anchor) == 1
fault = source.replace(anchor, 'return false; }')
results = {}
for name, code in [('bounded_fault',fault.replace('(1u << 30)', '20000u')), ('unbounded_fault',fault.replace('while ((uint32_t)(esp_cpu_get_cycle_count() - start) < FLUE_IWDT_MAX_WAIT_CYCLES)', 'while (true)'))]:
    # Match the actual generated bound spelling below, fail rather than silently mis-test.
    if name == 'unbounded_fault':
        import re
        code, n = re.subn(r'while \(\(uint32_t\)\(esp_cpu_get_cycle_count\(\) - \w+\) < FLUE_IWDT_MAX_WAIT_CYCLES\)', 'while (true)', fault)
        assert n == 1
    else:
        assert code != fault
    exe = compile_source(code,OUT/(name+'.c'))
    results[name] = m.run(exe, core=0, dir=0, trace_exp=m.NOEXP)
    (OUT/(name+'.trace.txt')).write_text(results[name]['stderr'])
(OUT/'fault-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({k: {"outcome": v["outcome"], "metrics": v["stderr"].splitlines()[-1]} for k,v in results.items()},indent=2))
