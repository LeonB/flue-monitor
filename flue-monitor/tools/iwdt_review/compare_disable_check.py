"""Compare removal of the final disable read-back without changing production.

Runs the existing matrix unchanged for each variant. The separate
probe_disable_check_fault.py measures lost detection with a synthetic fault.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import iwdt_dualcore_model as model

HERE = Path(__file__).resolve().parent
OUT = model.PROJECT / '.cache/iwdt-disable-check-comparison'
OUT.mkdir(parents=True, exist_ok=True)
source = (model.PROJECT / 'cmake/iwdt_transition.c.inc').read_text()
old = '''ok = !flue_iwdt_write_protect_is_open()
              && flue_iwdt_stage0_ticks() == IWDT_STAGE0_TIMEOUT_US
              && flue_iwdt_stage1_ticks() == IWDT_STAGE1_TIMEOUT_US;'''
assert source.count(old) == 1
candidate = OUT / 'without_final_disable_check.c.inc'
candidate.write_text(source.replace(old, 'ok = true;'))
runner = (HERE / 'run_review.py').read_text()
env = dict(os.environ, PYTHONPATH=str(HERE))
summaries = {}
for name, inc in [('current', None), ('without_check', candidate)]:
    directory = OUT / name
    text = runner.replace("OUT = Path('/tmp/flue-iwdt-v3-review')", f'OUT = Path({str(directory)!r})')
    text = text.replace('OUT.mkdir(exist_ok=True)', 'OUT.mkdir(parents=True, exist_ok=True)')
    if inc:
        text = text.replace('m.build(v, 0, OUT)', f'm.build(v, 0, OUT, proposal_inc=Path({str(inc)!r}) if v == "proposal" else None)')
    script = OUT / f'{name}_matrix.py'
    script.write_text(text)
    with (OUT / f'{name}.log').open('w') as log:
        subprocess.run([sys.executable, str(script)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    results = json.loads((directory / 'review-results.json').read_text())
    summaries[name] = dict(scenarios=len(results), runs=sum(r['runs'] for r in results),
                           failures=sum(not r['passed'] for r in results))
    print(name, summaries[name], flush=True)
(OUT / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
