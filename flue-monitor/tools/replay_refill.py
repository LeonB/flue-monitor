"""Compare actual old/new C detectors on a reconstruction of retained history.

This never contacts a monitor or notification service. Interpolated ten-second
values are assumptions, not recovered sensor data. No transport is simulated.
"""
import ctypes
import datetime
import json
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tools/fixtures/refill-20261116.json'


def run():
    data = json.loads(FIXTURE.read_text())
    samples = sorted((-age, temp, rate) for age, temp, rate, _ in data['samples'])
    events = sorted((-age, event) for age, event in data['events'])
    anchor = data['captured_at_estimate']
    tz = ZoneInfo('Europe/Amsterdam')

    def clock(t):
        return datetime.datetime.fromtimestamp(anchor + t, tz).strftime('%H:%M:%S')

    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        # Freeze the pre-action detector, independent of the working-tree edits.
        baseline = 'c557d2009fa1a063925e8ad211f2e1c9fcd3b668'
        old = directory / 'old'
        old.mkdir()
        for name in ('refill_rule.h', 'refill_rule.c'):
            content = subprocess.check_output(
                ['git', 'show', f'{baseline}:flue-monitor/main/{name}'], cwd=ROOT, text=True)
            (old / name).write_text(content)
        libraries = {}
        for label, source in [('old', old / 'refill_rule.c'), ('new', ROOT / 'main/refill_rule.c')]:
            library = directory / f'{label}.dylib'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-shared', '-fPIC', str(source), '-o', str(library)], check=True)
            lib = ctypes.CDLL(str(library))
            lib.refill_rule_reset.argtypes = [ctypes.c_void_p]
            lib.refill_rule_sample.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_bool,
                                              ctypes.c_float, ctypes.c_float, ctypes.c_float]
            if label == 'new':
                lib.refill_rule_sample.argtypes = lib.refill_rule_sample.argtypes + [ctypes.c_float]
                lib.refill_rule_event.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int64]
            lib.refill_rule_sample.restype = ctypes.c_bool
            libraries[label] = lib

        results = {}
        # Try both interpolating the recorded regression and using segment slopes.
        for rate_model in ('interpolated_regression', 'segment_slope'):
            for label, lib in libraries.items():
                state = (ctypes.c_longdouble * 32)()
                lib.refill_rule_reset(state)
                event_index = segment = 0
                triggers = []
                for t in range(samples[0][0], samples[-1][0] + 1, 10):
                    while event_index < len(events) and events[event_index][0] <= t:
                        when, event = events[event_index]
                        if label == 'new':
                            lib.refill_rule_event(state, event.encode(), (when - samples[0][0]) * 1000)
                        elif event in ('cold_start', 'added_wood', 'stove_off'):
                            lib.refill_rule_reset(state)
                        event_index += 1
                    while segment + 1 < len(samples) - 1 and samples[segment + 1][0] <= t:
                        segment += 1
                    start, a, ra = samples[segment]
                    end, b, rb = samples[segment + 1]
                    fraction = (t - start) / (end - start)
                    temperature = a + fraction * (b - a)
                    rate = ra + fraction * (rb - ra) if rate_model == 'interpolated_regression' else (b - a) * 60 / (end - start)
                    # Do not bridge long missing sections as if measured.
                    args = [state, (t - samples[0][0]) * 1000, end - start <= 480, temperature, rate, 80]
                    if label == 'new':
                        args.append(60)
                    if lib.refill_rule_sample(*args):
                        triggers.append({'estimated_time': clock(t), 'temperature_c': round(temperature, 1)})
                results[f'{label}/{rate_model}'] = triggers
        print(json.dumps({'source': data['source'], 'time_uncertainty_s': data['time_uncertainty_s'],
                          'events': [{'estimated_time': clock(t), 'event': e} for t, e in events],
                          'reconstructed_candidates': results,
                          'limitation': 'Reconstructed candidate times only; no proof of raw-sample state or actual ntfy delivery.'}, indent=2))
        for model in ('interpolated_regression', 'segment_slope'):
            assert len(results[f'old/{model}']) == 1
            assert len(results[f'new/{model}']) == 2


if __name__ == '__main__':
    run()
