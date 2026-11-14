"""Run one Unity case in an ESP32 QEMU image, retaining the UART transcript.

Only emulator files are used. No serial port or physical device is accessed.
"""
import argparse
from pathlib import Path
import selectors
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--qemu', required=True)
parser.add_argument('--flash', required=True, type=Path)
parser.add_argument('--efuse', required=True, type=Path)
parser.add_argument('--log', required=True, type=Path)
parser.add_argument('--case', required=True)
parser.add_argument('--timeout', type=float, default=60)
parser.add_argument('--disable-watchdog-expiry', action='store_true')
args = parser.parse_args()
command = [args.qemu, '-nographic', '-machine', 'esp32', '-m', '2M',
           '-nic', 'none', '-monitor', 'none', '-snapshot',
           '-drive', f'file={args.flash.resolve()},if=mtd,format=raw',
           '-drive', f'file={args.efuse.resolve()},if=none,format=raw,id=efuse',
           '-global', 'driver=nvram.esp32.efuse,property=drive,value=efuse']
if args.disable_watchdog_expiry:
    command += ['-global', 'driver=timer.esp32.timg,property=wdt_disable,value=true']
process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
transcript = bytearray()
ready = None
sent = False
started = time.monotonic()
try:
    while time.monotonic() - started < args.timeout:
        for key, _ in selector.select(0.1):
            chunk = key.fileobj.read1(8192)
            transcript.extend(chunk)
            if ready is None and b'Press ENTER' in transcript:
                ready = time.monotonic()
        # Unity flushes UART RX before reading a command; do not send too early.
        if not sent and ready is not None and time.monotonic() - ready > 0.2:
            process.stdin.write(f'"{args.case}"\n'.encode())
            process.stdin.flush()
            sent = True
        if b'1 Tests' in transcript or b':FAIL:' in transcript or b':IGNORE:' in transcript:
            break
        if process.poll() is not None:
            break
finally:
    process.terminate()
    try:
        process.wait(3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    selector.close()
args.log.write_bytes(transcript)
passed = f'{args.case}:PASS'.encode() in transcript
failed = any(marker in transcript for marker in [b':FAIL:', b':IGNORE:', b'panic\'ed', b'abort()'])
print(f'{args.case}: {"PASS" if passed and not failed else "FAIL/INCOMPLETE"}')
print(f'Watchdog expiry disabled: {args.disable_watchdog_expiry}; log: {args.log}')
raise SystemExit(0 if passed and not failed else 1)
