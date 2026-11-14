"""Compare the reorder+mode-flag alternative with v3 in the existing bounded model.

No hardware access. Timing and ordered APB/DRAM assumptions are those of
 iwdt_dualcore_model.py; a model counterexample is not a silicon reproduction.
"""
import concurrent.futures
import itertools
import json
from pathlib import Path
import iwdt_dualcore_model as model

HERE = Path(__file__).resolve().parent
OUT = model.PROJECT / '.cache/iwdt-minimal-comparison'
executables = {}
for name in ('minimal', 'v3'):
    directory = OUT / name
    directory.mkdir(parents=True, exist_ok=True)
    alternative = HERE / 'minimal_iwdt_transition.c.inc' if name == 'minimal' else None
    executables[name] = model.build('proposal', 0, directory, proposal_inc=alternative)

jobs = []
for order, apb, delay, core, direction in itertools.product((0, 1), (4, 10), (480, 2160), (0, 1), (0, 1)):
    params = dict(order=order, apb=apb, delay=delay, core=core, dir=direction,
                  exp_from=-10500 if not direction else 1000, exp_to=2000)
    for name in executables:
        jobs.append((name, params))

def run(job):
    name, params = job
    result = model.run(executables[name], **params)
    if result['bad_final']:
        offset, tick = result['first_bad_final']
        trace = model.run(executables[name], **params, trace_exp=offset, trace_tick=tick)
        filename = '-'.join(f'{k}{v}' for k, v in params.items()) + '.trace.txt'
        (OUT / name / filename).write_text(trace['stderr'] + '\n')
    return dict(variant=name, params=params, **result)

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run, jobs))
(OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
for name in executables:
    rows = [r for r in results if r['variant'] == name]
    print(name, json.dumps({key: sum(r[key] for r in rows)
                          for key in ('runs', 'ok', 'panic', 'reset', 'abort', 'deadlock', 'bad_final')}), flush=True)
