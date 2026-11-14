"""Bounded regression matrix. Model evidence only, never accesses hardware.

Normal cases require OK and intact short-stage/stage1 invariants. Deliberately
expired or stalled cases have separate, explicit fault expectations. All raw
outcomes are retained; no aggregate 'healthy' label hides a reset.
"""
import concurrent.futures
import itertools
import json
from pathlib import Path
import iwdt_dualcore_model as m

OUT = Path('/tmp/flue-iwdt-v3-review')
OUT.mkdir(exist_ok=True)
exes = {v: m.build(v, 0, OUT) for v in ['sdk', 'deployed', 'proposal']}
jobs = []
for variant in ['sdk', 'deployed', 'proposal']:
    for core in (0, 1):
        jobs.append(('baseline', variant, dict(core=core, exp_from=-10500, exp_to=1500)))
for order, apb, delay, core, direction in itertools.product((0, 1), (4, 10), (480, 2160), (0, 1), (0, 1)):
    jobs.append(('normal', 'proposal', dict(order=order, apb=apb, delay=delay, core=core, dir=direction,
                                         exp_from=-10500 if not direction else 1000, exp_to=2000)))
for core, direction, order in itertools.product((0, 1), (0, 1), (0, 1)):
    jobs.append(('tick', 'proposal', dict(core=core, dir=direction, order=order, exp_none=1,
                 tick_from=-1000, tick_to=2000)))
    jobs.append(('tick-exp', 'proposal', dict(core=core, dir=direction, order=order,
                 exp_from=-7000 if not direction else 1000, exp_to=1500, exp_step=17,
                 tick_from=-1000, tick_to=1500, tick_step=71)))
# Stalls are explicit stress cases: visible watchdog faults are retained, not called healthy.
for pc, length, core in itertools.product((0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26), (40,9500,20000), (0,1)):
    jobs.append(('stall', 'proposal', dict(stall_pc=pc, stall_len=length, core=core,
                                         exp_from=-10500, exp_to=1000, exp_step=97)))
for core in (0,1):
    jobs.append(('hung', 'proposal', dict(core=core, hung=1, exp_from=1, exp_to=20)))
    jobs.append(('expired', 'proposal', dict(core=core, dir=1, exp_from=-10, exp_to=-1)))
    jobs.append(('budget', 'proposal', dict(core=core, counter=39, exp_from=-10, exp_to=-1)))
    jobs.append(('periodic', 'proposal', dict(core=core, dir=0, exp_none=1, tick_count=4,
                    tick_period=5000, tick_from=-500, tick_to=500, tick_step=25)))

def execute(job):
    label, variant, params = job
    r = m.run(exes[variant], **params)
    safe = r['bad_final'] == 0 and r['viol_cycles_max'] == 0 and r['stage1_bad_max'] == 0
    if label == 'baseline':
        passed = (r['bad_final'] > 0 or r['panic'] > 0 or r['viol_cycles_max'] > 0) if variant == 'sdk' or (variant == 'deployed' and params['core'] == 0) else safe and r['ok'] == r['runs']
    elif label == 'hung': passed = safe and r['reset'] == r['runs']
    elif label in ('expired', 'budget'): passed = safe and r['panic'] == r['runs']
    elif label == 'stall': passed = safe and r['deadlock'] == 0
    else: passed = safe and r['ok'] == r['runs']
    return dict(label=label, variant=variant, params=params, passed=passed, **r)

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for r in pool.map(execute, jobs):
        results.append(r)
        if not r['passed']:
            print('FAIL', r, flush=True)
        elif len(results) % 20 == 0:
            print('progress',len(results),'/',len(jobs),flush=True)
(OUT/'review-results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(dict(scenarios=len(results), runs=sum(r['runs'] for r in results), failures=sum(not r['passed'] for r in results)), indent=2))
raise SystemExit(any(not r['passed'] for r in results))
