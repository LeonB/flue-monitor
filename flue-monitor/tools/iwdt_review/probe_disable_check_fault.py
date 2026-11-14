"""Synthetic diagnostic-coverage probe; not an asserted hardware failure mode.

Run compare_disable_check.py first. Inject stage0=40 immediately after the C
store max=0, beyond the model's ordinary ordered-memory/ownership assumptions.
"""
import json
from pathlib import Path
import subprocess
import iwdt_dualcore_model as model

OUT = model.PROJECT / '.cache/iwdt-disable-check-comparison'
anchor = 'static void shared_store(volatile uint32_t *p, uint32_t v) { *p = v; advance(2); }'
replacement = '''static void shared_store(volatile uint32_t *p, uint32_t v) {
    *p = v;
    if (p == &_lx_intr_livelock_max && v == 0 && DIR == 0) {
        hw_stage0 = 40;
        TR("SYNTHETIC FAULT: stage0 changed to 40 after max=0");
    }
    advance(2);
}'''
results = {}
for name in ('current', 'without_check'):
    original = OUT / name / 'proposal_0.c'
    source = original.read_text()
    assert source.count(anchor) == 1
    c = OUT / name / 'fault_probe.c'
    # NOEXP normally serves timing calibration and bypasses final-state checks.
    # This probe needs those checks even without a scheduled expiry.
    calibration = f'    if (expiry_offset == {model.NOEXP} && tick_offset == {model.NOTICK}) return R_OK;\n'
    assert source.count(calibration) == 1
    source = source.replace(calibration, '')
    c.write_text(source.replace(anchor, replacement))
    exe = c.with_suffix('')
    subprocess.run(['cc', '-std=c11', '-O2', '-Wno-deprecated-declarations', str(c), '-o', str(exe)], check=True)
    result = model.run(exe, core=0, dir=0, trace_exp=model.NOEXP)
    (OUT / name / 'fault_probe.trace.txt').write_text(result['stderr'] + '\n')
    results[name] = result['outcome']
print(json.dumps(results, indent=2))
(OUT / 'fault-probe-results.json').write_text(json.dumps(results, indent=2) + '\n')
