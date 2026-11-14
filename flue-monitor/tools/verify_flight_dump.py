"""Decode a deliberate self-test capture and verify stack/recorder contents.

Run with the ESP-IDF Python environment. Keeps raw memory local and prints only
verification results, never arbitrary strings or heap contents. --expect-heap
also checks heap/PSRAM patterns from legacy full-heap builds. Real crashes do
not contain these deliberate test markers; do not use this as their validator.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import struct
from elftools.elf.elffile import ELFFile
from esp_coredump.corefile.loader import ESPCoreDumpFileLoader

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--serial', type=Path, required=True)
parser.add_argument('--elf', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--expect-heap', action='store_true',
                    help='Verify heap patterns in legacy full-heap self-test dumps only')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
raw = args.serial.read_bytes()
ends = list(re.finditer(rb'={5,} CORE DUMP END ={5,}', raw))
if not ends:
    raise SystemExit('No complete UART core dump found')
end = ends[-1].start()
starts = list(re.finditer(rb'={5,} CORE DUMP START ={5,}\r?\n',raw[:end]))
assert starts, 'Dump end has no preceding start'
payload = raw[starts[-1].end():end]  # skip earlier dumps interrupted by a reset
lines = [line.strip() for line in payload.splitlines() if line.strip()]
assert all(re.fullmatch(rb'[A-Za-z0-9+/]+=*', line) for line in lines), 'Unexpected text inside Base64 dump'
b64 = args.output/'core.b64'
b64.write_bytes(b'\n'.join(lines)+b'\n')
loader = ESPCoreDumpFileLoader(str(b64), is_b64=True)
loader.create_corefile(exe_name=str(args.elf))  # SDK validates checksum and executable identity
core_path = args.output/'core.elf'
shutil.copyfile(loader.core_elf_file, core_path)
with args.elf.open('rb') as file:
    firmware = ELFFile(file)
    assert firmware.elfclass == 32
    symbols = {sym.name: sym.entry for sym in firmware.get_section_by_name('.symtab').iter_symbols()}
with core_path.open('rb') as file:
    core = ELFFile(file)
    segments = [(int(seg['p_vaddr']),seg.data()) for seg in core.iter_segments() if seg['p_type']=='PT_LOAD']

def memory(address, length):
    for start, data in segments:
        offset = address-start
        if offset>=0 and offset+length<=len(data):
            return data[offset:offset+length]
    raise AssertionError(f'Missing memory region at 0x{address:x}, length {length}')

state = memory(int(symbols['flue_test_state']['st_value']),24)
magic,seed,size,internal,psram,stack = struct.unpack('<6I',state)
assert magic==0x46545331 and size==256, 'Self-test state not captured'
if args.expect_heap:
    assert memory(internal,size)==bytes((i*17+seed)&255 for i in range(size)), 'Internal heap pattern differs'
    assert memory(psram,size)==bytes((i*29+(seed^0xa5))&255 for i in range(size)), 'PSRAM heap pattern differs'
assert struct.unpack('<4I',memory(stack,16))==(0x53544143,0x4b544553,0x54524143,0x454f4b21), 'Stack pattern differs'

trace = memory(int(symbols['flue_trace']['st_value']),int(symbols['flue_trace']['st_size']))
trace_magic,version,*heads = struct.unpack_from('<6I',trace)
assert trace_magic==0x46545231 and version==1, 'Recorder state missing'
records=[]
for cpu in range(2):
    for bank,capacity,base in [(0,96,24+cpu*96*16),(1,32,24+2*96*16+cpu*32*16)]:
        head=heads[cpu*2+bank]
        for seq in range(max(1,head-capacity+1),head+1):
            actual,clock,event,core_id,flags,value=struct.unpack_from('<IIHBBI',trace,base+((seq-1)%capacity)*16)
            if actual!=seq:continue  # an interrupted writer is deliberately uncommitted
            assert core_id==cpu
            records.append({'core':cpu,'bank':bank,'sequence':seq,'clock':clock,'event':event,'flags':flags,'value':value})
assert any(r['event']==21 and r['value']==0x43524153 for r in records), 'Crash marker missing'
assert any(r['event']==20 and r['value']==299 for r in records), 'Wrapped-ring marker missing'
assert any(r['bank']==1 for r in records), 'No sleep events captured'
report={'checksum_valid':True,'internal_heap_pattern':True if args.expect_heap else None,
        'psram_heap_pattern':True if args.expect_heap else None,'stack_pattern':True,
        'recorder_valid':True,'records':len(records),'sleep_records':sum(r['bank']==1 for r in records),
        'core_elf':str(core_path.resolve()),'firmware_elf':str(args.elf.resolve())}
(args.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
(args.output/'recorder.json').write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(report,indent=2))
