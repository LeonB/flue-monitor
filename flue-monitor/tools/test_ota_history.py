"""Exercise the OTA client against a real local HTTP server and bounded rings."""
from pathlib import Path
import http.server
import json
import struct
import tempfile
import threading
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
        assert ota.decode_history((out/'history-before.bin').read_bytes())['samples'] == ota.decode_history(before)['samples']
        assert ota.history_contains(ota.decode_history((out/'history-before.bin').read_bytes()), ota.decode_history((out/'history-after.bin').read_bytes()))
        assert json.loads((out/'verified.json').read_text())['samples_preserved'] == 2
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
print('PASS external backup/restore/read-back, plateau retention, failure diagnostics and no upload retry')

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
