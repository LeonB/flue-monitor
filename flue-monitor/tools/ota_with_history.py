#!/usr/bin/env python3
"""OTA with an external graph snapshot; no third-party Python packages needed."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never send the OTA secret to a redirect target.


def decode_history(blob):
    if len(blob) != 6296:
        raise ValueError('Unexpected history snapshot size')
    wall, version, count, events, elapsed = struct.unpack_from('<qIIII', blob)
    if version not in (1, 2) or (version == 1 and elapsed) or count > 360 or events > 64 or wall < 0:
        raise ValueError('Unsupported history snapshot')
    return {
        'saved_at': wall, 'version': version, 'elapsed_s': elapsed,
        'samples': [struct.unpack_from('<IffI', blob, 24 + 16*i) for i in range(count)],
        'events': [struct.unpack_from('<II', blob, 5784 + 8*i) for i in range(events)],
    }


def stamp_history(blob):
    decode_history(blob)
    result = bytearray(blob)
    struct.pack_into('<q', result, 0, int(time.time()))
    return bytes(result)


def prepare_restore(blob):
    snapshot = decode_history(blob)
    if snapshot['saved_at'] <= 0:
        raise ValueError('Snapshot has no Mac capture timestamp')
    elapsed = int(time.time()) - snapshot['saved_at']
    if not 0 <= elapsed <= 0xffffffff:
        raise ValueError('Invalid elapsed time since backup')
    result = bytearray(blob)
    struct.pack_into('<I', result, 8, 2)
    struct.pack_into('<I', result, 20, elapsed)
    return bytes(result)


def history_contains(before, after):
    for age, temp, rate, zone in before['samples']:
        epoch = before['saved_at'] - age
        if any(abs(after['saved_at']-a-epoch) <= 2 and abs(t-temp) < .01 and
               abs(r-rate) < .01 and z == zone for a, t, r, z in after['samples']):
            continue
        timeline = [(after['saved_at']-a, t, r, z) for a, t, r, z in after['samples']]
        if timeline and len(timeline) == 360 and epoch < timeline[0][0]:
            continue  # The bounded ring keeps the newest points.
        # Stable-history compression can replace the old plateau tail with a
        # newer endpoint; the original point must remain on the same plateau.
        left = next((x for x in reversed(timeline) if x[0] <= epoch), None)
        right = next((x for x in timeline if x[0] >= epoch), None)
        if not (left and right and all(abs(x[1]-temp) < .01 and abs(x[2]-rate) <= .051 and x[3] == zone
                                     for x in (left, right))):
            return False
    for age, event in before['events']:
        epoch = before['saved_at'] - age
        if not any(abs(after['saved_at']-a-epoch) <= 2 and ev == event for a, ev in after['events']):
            if len(after['events']) == 64 and epoch < after['saved_at'] - after['events'][0][0]:
                continue
            return False
    return True


def flash_usb(port, expected_mac, image, out):
    def run(*arguments):
        result = subprocess.run(['esptool', '--chip', 'esp32', '--port', port, *arguments],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with (out / 'usb.log').open('a') as log:
            log.write(result.stdout)
        if result.returncode:
            raise RuntimeError('USB operation failed; inspect usb.log')
        return result.stdout

    identity = run('--before', 'default-reset', '--after', 'no-reset', 'read-mac')
    addresses = re.findall(r'(?i)(?:Base )?MAC:\s*([0-9a-f:]{17})', identity)
    if expected_mac.lower() not in [a.lower() for a in addresses]:
        raise RuntimeError('USB device MAC does not match the selected monitor; nothing flashed')
    table = out / 'partition-table.bin'
    run('--before', 'no-reset', '--after', 'no-reset', 'read-flash', '0x8000', '0x1000', str(table))
    applications = {}
    data = table.read_bytes()
    for pos in range(0, len(data), 32):
        magic, kind, subtype, offset, size, name, flags = struct.unpack_from('<HBBII16sI', data, pos)
        if magic != 0x50aa:
            break
        if kind == 0:
            applications[name.rstrip(b'\0').decode()] = (offset, size)
    expected = {'ota_0': 0x20000, 'ota_1': 0x1a0000}
    arguments = []
    for name, offset in expected.items():
        if name not in applications or applications[name][0] != offset or applications[name][1] < image.stat().st_size:
            raise RuntimeError('Unexpected OTA partition layout; nothing flashed')
        arguments += [hex(offset), str(image)]
    # Keep the existing selected slot, settings, bootloader and partition table.
    # Both application slots receive the same image so either selection is valid.
    run('--before', 'no-reset', '--after', 'hard-reset', 'write-flash', *arguments)


def update(project, host, image, without_history=False, usb_port=None, expected_mac=None):
    if not re.fullmatch(r'[A-Za-z0-9._:-]+', host):
        raise ValueError('Invalid device hostname')
    text = (project / 'main/secrets.h').read_text()
    match = re.search(r'^#define\s+OTA_SECRET\s+"([^"\r\n]+)"', text, re.M)
    if not match:
        raise ValueError('OTA_SECRET missing')
    query = urllib.parse.urlencode({'secret': match.group(1)})
    opener = urllib.request.build_opener(NoRedirect)

    def request(path, body=None, timeout=15):
        req = urllib.request.Request(f'http://{host}{path}?{query}', data=body,
                                     headers={'Content-Type': 'application/octet-stream', 'Connection': 'close'})
        with opener.open(req, timeout=timeout) as response:
            return response.read()

    data = image.read_bytes()
    out = project / '.cache/ota-history' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    record = {'host': host, 'image_sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    snapshot = None
    if not without_history:
        snapshot = stamp_history(request('/ota/history'))
        decode_history(snapshot)
        (out / 'history-before.bin').write_bytes(snapshot)
        print(f'Graph backup saved to {out / "history-before.bin"}', flush=True)
    (out / 'upload.json').write_text(json.dumps(record, indent=2) + '\n')
    frozen_image = out / 'firmware.bin'
    frozen_image.write_bytes(data)
    # Deliberately one upload. Never retry a mutating request on an uncertain result.
    if usb_port:
        if not expected_mac or not re.fullmatch(r'[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}', expected_mac):
            raise ValueError('USB flash requires --expected-mac')
        flash_usb(usb_port, expected_mac, frozen_image, out)
    else:
        try:
            reply = request('/ota', data, timeout=180)
        except urllib.error.HTTPError as error:
            record.update(http_status=error.code, response=error.read(1024).decode(errors='replace'))
            (out / 'upload.json').write_text(json.dumps(record, indent=2) + '\n')
            raise RuntimeError('Device rejected OTA; diagnostic and graph backup retained') from None
        (out / 'ota-response.txt').write_bytes(reply)
    print('Firmware uploaded; waiting for restart.', flush=True)
    if snapshot is None:
        return out
    time.sleep(2)
    last_error = None
    for _ in range(60):
        try:
            current = stamp_history(request('/ota/history'))
            decode_history(current)
            break
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            last_error = type(error).__name__
            time.sleep(2)
    else:
        raise RuntimeError(f'Monitor not ready ({last_error}); backup retained in {out}')
    expected = decode_history(snapshot)
    if not history_contains(expected, decode_history(current)):
        request('/ota/history', prepare_restore(snapshot))  # One restore, then independently read it back.
        current = stamp_history(request('/ota/history'))
    (out / 'history-after.bin').write_bytes(current)
    if not history_contains(expected, decode_history(current)):
        raise RuntimeError(f'History verification failed; backup retained in {out}')
    (out / 'verified.json').write_text(json.dumps({'samples_preserved': len(expected['samples']),
                                                'events_preserved': len(expected['events'])}, indent=2) + '\n')
    print('Graph history verified after restart.', flush=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('host')
    parser.add_argument('--image', type=Path)
    parser.add_argument('--usb-port', help='USB recovery instead of OTA; activate ESP-IDF first')
    parser.add_argument('--expected-mac', help='Required USB device identity check')
    parser.add_argument('--without-history', action='store_true', help='Explicit recovery/legacy update without automatic graph backup')
    args = parser.parse_args()
    project = args.project.resolve()
    image = args.image or project / 'build' / (project.name + '.bin')
    try:
        update(project, args.host, image, args.without_history, args.usb_port, args.expected_mac)
    except Exception as error:
        # urllib exception strings may embed the secret-bearing URL.
        print(f'OTA failed ({type(error).__name__}). No automatic upload retry; inspect .cache/ota-history.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
