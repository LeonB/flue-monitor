#!/bin/sh
# Build only: preserves the normal config and never contacts a device.
# Pass --size to use -Os while retaining ELF debug symbols and all features.
set -eu
mode=""
self_test=""
for option in "$@"; do
  case "$option" in
    --size) mode=--size ;;
    --self-test) self_test=--self-test ;;
    *) echo "Usage: sh tools/build_watchdog_diagnostics.sh [--size] [--self-test]" >&2; exit 2 ;;
  esac
done
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
. ./activate-idf.sh
diagnostic_dir="$project_dir/build/watchdog-diagnostics"
if [ "$mode" = --size ]; then diagnostic_dir="$diagnostic_dir-size"; fi
if [ "$self_test" = --self-test ]; then diagnostic_dir="$diagnostic_dir-self-test"; fi
mkdir -p "$diagnostic_dir"
python - "$project_dir/sdkconfig" "$project_dir/sdkconfig.watchdog-diagnostics.defaults" "$diagnostic_dir/sdkconfig" "$mode" "$self_test" <<'PY'
from pathlib import Path
import re
import sys

baseline, overlay, output = map(Path, sys.argv[1:4])
config = baseline.read_text()
lines = overlay.read_text().splitlines()
if sys.argv[4] == '--size':
    lines += ['# CONFIG_COMPILER_OPTIMIZATION_DEBUG is not set',
              'CONFIG_COMPILER_OPTIMIZATION_SIZE=y',
              '# CONFIG_COMPILER_OPTIMIZATION_PERF is not set',
              '# CONFIG_COMPILER_OPTIMIZATION_NONE is not set']
if sys.argv[5] == '--self-test':
    lines += ['CONFIG_FLUE_DIAG_CRASH_TEST=y']
for line in lines:
    match = re.match(r'(CONFIG_\w+)=', line) or re.match(r'# (CONFIG_\w+) is not set$', line)
    if not match:
        continue
    key = match[1]
    config = re.sub(r'^(?:' + key + r'=.*|# ' + key + r' is not set)\n?', '', config, flags=re.M)
    config += line + '\n'
output.write_text(config)
PY
idf.py -B "$diagnostic_dir" -D "SDKCONFIG=$diagnostic_dir/sdkconfig" build
