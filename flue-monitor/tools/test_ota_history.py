"""Exercise the OTA client against a real local HTTP server and bounded rings."""
from pathlib import Path
import http.server
import json
import struct
import tempfile
import threading
import copy
import ota_with_history as ota


def blob(samples, events=(), wall=1800000000):
    data = struct.pack('<qIIII', wall, 2, len(samples), len(events), 0)
    data += b''.join(struct.pack('<IffI', *p) for p in samples) + bytes(16*(360-len(samples)))
    data += b''.join(struct.pack('<II', *e) for e in events) + bytes(8*(64-len(events)))
    return data


before = blob([(100, 200, 1, 2), (50, 150, -1, 2)], [(75, 2)])
current = before
uploads = restores = 0
fail_upload = False


class Server(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        assert self.path == '/ota/history?secret=test-secret'
        self.send_response(200)
        self.send_header('Content-Length', str(len(current)))
        self.end_headers()
        self.wfile.write(current)

    def do_POST(self):
        global current, uploads, restores
        data = self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/ota?secret=test-secret':
            uploads += 1
            assert data == b'firmware'
            if fail_upload:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'test OTA failure')
                return
            current = blob([(0, 140, -1, 2)])  # Simulate lost RAM across a restart.
        else:
            assert self.path == '/ota/history?secret=test-secret'
            decoded = ota.decode_history(data)
            elapsed = decoded['elapsed_s']
            current = blob([(a+elapsed,t,r,z) for a,t,r,z in decoded['samples']],
                           [(a+elapsed,e) for a,e in decoded['events']], wall=0)
            restores += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Server)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root/'main').mkdir()
        (root/'main/secrets.h').write_text('#define OTA_SECRET "test-secret"\n')
        image = root/'firmware.bin'
        image.write_bytes(b'firmware')
        ota.time.sleep = lambda _: None
        out = ota.update(root, f'127.0.0.1:{server.server_port}', image)
        assert uploads == restores == 1
        utc = json.loads((out/'history-before.json').read_text())
        ota.validate_utc_history(utc)
        assert utc['samples'][0]['timestamp'] == utc['captured_at'] - 100
        assert utc['events'][0]['timestamp'] == utc['captured_at'] - 75
        assert (out/'history-after.json').exists()
        assert ota.decode_history((out/'history-before.bin').read_bytes())['samples'] == ota.decode_history(before)['samples']
        assert ota.history_contains(ota.decode_history((out/'history-before.bin').read_bytes()), ota.decode_history((out/'history-after.bin').read_bytes()))
        assert json.loads((out/'verified.json').read_text())['samples_exactly_retained'] == 2
        fail_upload = True
        try:
            ota.update(root, f'127.0.0.1:{server.server_port}', image)
            raise AssertionError('Failed OTA was accepted')
        except RuntimeError:
            pass
        assert uploads == 2 and restores == 1  # No implicit retry.
        records = [json.loads(p.read_text()) for p in root.glob('.cache/ota-history/*/upload.json')]
        assert any(r.get('http_status') == 500 and r['response'] == 'test OTA failure' for r in records)
    # Compression may extend a flat plateau without losing the old graph value.
    assert ota.history_contains(ota.decode_history(blob([(100, 20, 0, 1), (50, 20, 0, 1)])),
                                ota.decode_history(blob([(100, 20, 0, 1), (0, 20, 0, 1)])))
    assert not ota.history_contains(ota.decode_history(before), ota.decode_history(blob([(0, 140, 0, 2)])))
    try:
        ota.decode_history(b'bad')
        raise AssertionError('Invalid snapshot accepted')
    except ValueError:
        pass
finally:
    server.shutdown()
    server.server_close()
# Replaying already-compressed history can remove points whose rate is more
# than .05 from one final neighbour: the old interpolation heuristic failed.
raw = [(i*240,20,rate,1) for i,rate in enumerate((-.08,-.04,0,-.08,-.12))]
old = ota.compressed_history(raw)
compacted = ota.compressed_history(old)
assert len(old) == 4 and len(compacted) == 2
as_snapshot = lambda points: {'saved_at': 1800000000,
    'samples': [(1800000000-t,c,r,z) for t,c,r,z in points], 'events': []}
report = ota.history_verification(as_snapshot(old), as_snapshot(compacted))
assert report['sample_retention'] == 'compression_equivalent' and report['samples_exactly_retained'] == 2
# Missing a real peak, altering zone/rate, or moving a point beyond clock
# uncertainty must still fail, even if the rest looks like a flat plateau.
peak = [(100,20,0,1),(200,80,4,1),(300,20,0,1)]
assert not ota.history_contains(as_snapshot(peak),as_snapshot([peak[0],peak[-1]]))
for changed in ([(100,21,0,1),(300,20,0,1)],[(100,20,0,2),(300,20,0,1)],
                [(100,20,.1,1),(300,20,0,1)],[(103,20,0,1),(300,20,0,1)]):
    assert not ota.history_contains(as_snapshot([peak[0],peak[-1]]),as_snapshot(changed))
# A two-second capture uncertainty and genuine new plateau endpoint are accepted.
assert ota.history_contains(as_snapshot([(100,20,0,1),(200,20,0,1)]),
                            as_snapshot([(102,20,0,1),(400,20,0,1)]))
full = as_snapshot([(1000+i*240,20+i,0,1) for i in range(360)])
old = as_snapshot([(100,10,0,1)])
old['events'] = [(1800000000-100,2)]
full['events'] = [(1800000000-(1000+i),2) for i in range(64)]
capacity = ota.history_verification(old, full)
assert capacity['sample_retention'] == 'bounded_capacity'
assert capacity['samples_evicted_by_capacity'] == 1
assert capacity['events_preserved'] == 0 and capacity['events_evicted_by_capacity'] == 1
print('PASS recompression-aware retention, exact/equivalent reporting and rejection of changed peaks/values/rates/zones/times')
print('PASS external backup/restore/read-back, plateau retention, failure diagnostics and no upload retry')

# Absolute UTC records survive delayed and repeated restores without changing
# their timestamps. The device's wall clock is never used for the conversion.
utc = ota.history_to_utc(ota.decode_history(before))
original = copy.deepcopy(utc)
for delay in (0, 3600, 86400, 31536000):
    restored = ota.decode_history(ota.utc_restore_payload(utc, now=utc['captured_at']+delay))
    assert ota.history_to_utc(restored)['samples'] == original['samples']
    assert ota.history_to_utc(restored)['events'] == original['events']
    assert utc == original
# The wire's firmware wall clock is ignored: Mac capture time is the anchor.
old_clock = ota.time.time
try:
    ota.time.time = lambda: 1800000000
    assert ota.history_to_utc(ota.decode_history(ota.stamp_history(blob([(100,20,0,1)],wall=42))))['samples'][0]['timestamp'] == 1799999900
finally:
    ota.time.time = old_clock
for mutate in (
    lambda b: b.update(version=99),
    lambda b: b.update(captured_at=True),
    lambda b: b.update(samples=[None]),
    lambda b: b['samples'][0].update(timestamp=b['captured_at']+1),
    lambda b: b['samples'][1].update(timestamp=b['samples'][0]['timestamp']-1),
    lambda b: b['samples'][0].update(temperature_c=float('nan')),
    lambda b: b['samples'][0].update(rate_c_per_min=float('inf')),
    lambda b: b['samples'][0].update(zone=4),
    lambda b: b['events'][0].update(event_id=-1),
):
    bad = copy.deepcopy(original);mutate(bad)
    try: ota.utc_restore_payload(bad,now=1800000100);raise AssertionError('Invalid UTC backup accepted')
    except ValueError: pass
for now in (original['captured_at']-1, original['captured_at']+0x100000000):
    try: ota.utc_restore_payload(original,now=now);raise AssertionError('Invalid clock/range accepted')
    except ValueError: pass
# Same-second taps are real records; one event must not satisfy two expected taps.
twice = ota.decode_history(blob([],[(75,2),(75,2)]))
assert not ota.history_contains(twice,ota.decode_history(blob([],[(75,2)])))
print('PASS UTC timestamps across delayed/repeated restores, invalid data, clock rollback, range and duplicate events')

# Verify the USB path stops before programming the wrong device/layout.
from types import SimpleNamespace
with tempfile.TemporaryDirectory() as d:
    out = Path(d)
    image = out/'firmware.bin'; image.write_bytes(b'firmware')
    calls = []
    good_mac = '8c:94:df:0b:be:fc'
    wrong_mac = False
    wrong_table = False
    original_run = ota.subprocess.run
    def fake_run(command, **kwargs):
        calls.append(command)
        if 'read-mac' in command:
            mac = '00:11:22:33:44:55' if wrong_mac else good_mac
            return SimpleNamespace(returncode=0, stdout='MAC: '+mac+'\n')
        if 'read-flash' in command:
            records = [(1,2,0x9000,0x6000,b'nvs'),(0,0x10,0x20000,1536000,b'ota_0'),
                       (0,0x11,0x1a0000 if not wrong_table else 0x190000,1536000,b'ota_1')]
            table = b''.join(struct.pack('<HBBII16sI',0x50aa,t,st,offset,size,name,0) for t,st,offset,size,name in records)
            Path(command[-1]).write_bytes(table+bytes([255])*(4096-len(table)))
        return SimpleNamespace(returncode=0, stdout='OK\n')
    ota.subprocess.run = fake_run
    try:
        wrong_mac = True
        try: ota.flash_usb('test-port',good_mac,image,out);raise AssertionError('Wrong MAC accepted')
        except RuntimeError: pass
        assert len(calls)==1 and not any('write-flash' in c for c in calls)
        wrong_mac = False;wrong_table = True;calls.clear()
        try: ota.flash_usb('test-port',good_mac,image,out);raise AssertionError('Wrong partition accepted')
        except RuntimeError: pass
        assert not any('write-flash' in c for c in calls)
        wrong_table = False;calls.clear();ota.flash_usb('test-port',good_mac,image,out)
        write = next(c for c in calls if 'write-flash' in c)
        assert write[write.index('write-flash')+1:]==['0x20000',str(image),'0x1a0000',str(image)]
    finally:
        ota.subprocess.run = original_run
print('PASS USB MAC/layout verification and application-only write addresses')
