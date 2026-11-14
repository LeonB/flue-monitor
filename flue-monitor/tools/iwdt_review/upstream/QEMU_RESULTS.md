# QEMU validation

Espressif QEMU 9.2.2 (`esp_develop_9.2.2_20260417`, macOS arm64),
ESP-IDF v6.0.3. Both images use the same native Unity test app, two CPUs,
2 MB PSRAM, 800 ms IWDT, and virtual eFuses selecting ESP32 revision 3.0.
The candidate compiles the exported SDK sources. The baseline compiles the
installed, unmodified SDK. Neither physical device was accessed.

| Test | Original SDK | Candidate |
| --- | --- | --- |
| Tick/mode retention, watchdog expiry disabled | FAIL: max=39, stage0=40 instead of disabled mode | PASS: 32 rounds per core, no skip |
| Light sleep, 20 ms timer, watchdog expiry disabled | LoadStorePIFAddrError at 0x3ff5d054 | Same exception/address |
| Watchdog expiry enabled, instruction counting shift=0 | CPU1 IWDT panic before case execution | CPU1 IWDT panic before case execution |

The tick result is a real failing/passing regression control executing compiled
Xtensa firmware, but it covers mode/register retention only. The emulator's
`wdt_disable=true` prevents expiry events; it does not remove register writes
or their read-backs. This is also the default in IDF 6.0.3 qemu_ext.py. It does
not demonstrate correct handling of an interrupt during a transition.

The sleep exception decodes to `rtc_sleep_pd`, the BBPD_CTRL access, in both
images. Sleep completion is therefore not validated in this emulator setup.
An initial 2 ms sleep returned ESP_ERR_SLEEP_TOO_SHORT_SLEEP_DURATION (258).
The native test now requests 20 ms to leave room for transition overhead; its
checks and production code were not weakened. Even with that correction the
RTC exception remains.

Active-watchdog runs cannot yet serve as regression evidence: both images
panic with CPU1 in the idle wait path. No production fix is inferred from this
emulator behavior. APB/DRAM ordering and physical watchdog timing still require
platform/hardware evidence.

## Reproduction

`run_qemu_case.py` accepts explicit QEMU, merged flash and eFuse paths, runs
one named Unity case and saves the UART transcript. It returns failure on
skip, panic, failed assertion or missing PASS. `--disable-watchdog-expiry`
is explicit in both the command and result; it is never silently enabled.

Example, from repository root (replace QEMU with the installed executable):

```sh
python3 flue-monitor/tools/iwdt_review/upstream/run_qemu_case.py \
  --qemu "$QEMU" \
  --flash flue-monitor/.cache/iwdt-hardware-test/candidate-20ms-qemu_flash.bin \
  --efuse flue-monitor/.cache/iwdt-hardware-test/build/qemu_efuse_eco3.bin \
  --case 'interrupt watchdog mode survives tick feeds on both cores' \
  --disable-watchdog-expiry --log /tmp/iwdt-qemu-tick.log
```

Artifacts and candidate/baseline UART transcripts are under
`flue-monitor/.cache/iwdt-hardware-test/`. The `candidate-20ms-*` and
`baseline-20ms-*` files preserve their binaries and exact ELFs. The build
configuration is restored to IWDT_USE_PATCH=ON after comparisons.

References:
- https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32/README.md
- https://github.com/espressif/esp-idf/blob/v6.0.3/tools/idf_py_actions/qemu_ext.py
