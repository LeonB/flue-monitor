# ESP-IDF upstream review package

Published draft: https://github.com/espressif/esp-idf/pull/19359. The PR is ported to master; this directory retains the v6.0.3 export and test evidence. See publication.json for exact commits and checkout. The SDK installation is unchanged. Temporary hardware testing is recorded below; no production deployment of this candidate is implied.

- `iwdt-transition.patch`: native SDK and Unity-test patch against v6.0.3.
- `src/`: readable patched SDK source files.
- `export_patch.py`: reproducible export from the project-local candidate.
- `PR_DESCRIPTION.md`: English PR draft with evidence and limits.

## Style and scope

The export removes project-specific prefixes from static functions/state/macros,
uses the existing `esp_int_wdt_` namespace for the cross-file function, declares
that function in the private header, moves includes to the include section,
splits assembly extern declarations, and replaces project history and hardcoded
800 ms examples with protocol comments. Four-space indentation, snake_case,
`s_` static state and existing IRAM attributes follow the surrounding SDK code.
It deliberately retains unconditional aborts: replacing them with configurable
assertions would change failure behavior. The assembly change only exports
three existing symbols.

Style reference:
https://docs.espressif.com/projects/esp-idf/en/latest/esp32/contribute/style-guide.html

This is not yet a master-targeted submission. Rebase against a named current
upstream commit before publication, including its updated chip/config guards.
Do not blindly apply the pinned generator to a different SDK revision.

## Acceptance work remaining

1. Keep the exported-source C harness and original-SDK failing controls current when rebasing.
2. Extend the successful native Unity hardware run to other configured timeouts/CPU frequencies and workaround-disabled builds.
   Fault injection needs an explicit hardware-test authorization.
3. Confirm APB-to-DRAM ordering and WPROTECT read-back with Espressif/platform
   documentation or hardware evidence. These remain merge-readiness questions.
4. Run the relevant upstream pre-commit hooks (not yet run for this export). The complete test app links; transition helpers and handler state are in IRAM/internal DRAM.
5. Review the PR text and CLA as the human contributor. Submit as draft if asking
   maintainers about the synchronization approach before hardware validation.

## Checks performed on this export

2026-11-02: `git apply --check` against the pinned clean SDK passed. int_wdt.c,
eco3_livelock_workaround.c and highint_hdl.S compiled using the existing diagnostic
compile commands and exported private header; objects were written under /tmp.
No link, deployment or hardware test was performed. Existing 407950-run model
results are historical algorithm evidence, not an execution of this export.

## Native Unity tests added

`main/test_int_wdt.c` is registered in the existing esp_system_unity_tests
CMake source list. Existing pytest `run_all_single_board_cases` discovers both
cases; no separate runner is required. The tests are compiled only for ESP32
with IWDT and the ECO3 workaround, and explicitly skip unaffected chip revisions.
The existing PSRAM CI configuration is the relevant configuration.

- 32 disable/tick/enable rounds per core check the actual stage registers and
  recovery budget. Ticks must not re-enable recovery while the mode is disabled.
- 100 timer-woken light sleeps per core check successful sleep and restored mode.

Tasks run sequentially on each core; Unity assertions run in the parent after
mode restoration. Existing pytest supplies the 60-second case timeout. These
are hardware integration tests, not deterministic injection of the short
transition race. They call the existing SDK entry point, with no test-only
implementation or production hooks.

The new translation unit was cross-compiled against real SDK/Unity headers,
using the diagnostic ESP32 flags plus Unity runner/priority definitions.
The complete test application has not been linked or executed. No hardware
results are claimed. The updated patch passes `git apply --check`.

## Full test-app build and hardware selection (2026-11-02)

The complete upstream Unity test application now builds and links with the
exported SDK patch and both new tests, PSRAM, 800 ms IWDT and the upstream
sleep-debug configuration. Build artifacts and validation.json are under
`.cache/iwdt-hardware-test/` in the flue-monitor project.

Hardware execution was not performed: the attached flue-display is an ESP32
revision 1.0, MAC 84:0d:8e:d2:a6:ec. The SDK's soc_has_cache_lock_bug() requires
revision >= 3.0, so both tests would skip. No flash was written. A slot backup
read failed and is not a usable restoration image. A suitable board is needed.

## Local host execution (2026-11-02)

From the repository root:

```sh
IWDT_UPSTREAM_DIR=flue-monitor/tools/iwdt_review/upstream/src python3 flue-monitor/tools/test_iwdt_transition.py
python3 flue-monitor/tools/test_iwdt_transition.py
python3 flue-monitor/tools/iwdt_review/run_review.py
```

The first command now extracts the actual exported transition and tick functions
and the SDK wrapper, rather than using the project-local transition fragment.
Only the hardware/interrupt primitives are stubbed. ASan/UBSan checks pass for
mode restoration, CPU progress gating, queued tick feeds, disabled-mode feeds
and the unaffected-chip wrapper's no-op behavior. An initial harness expectation
incorrectly expected that wrapper to feed on unaffected chips; it now explicitly
requires no feed and unchanged register state, matching the existing SDK guard.
No production change was made to satisfy this check.

These are local custom host harnesses, not an invocation of ESP-IDF's native
Linux pytest suite. The two-core matrix still uses the project-local candidate
and retains its documented ordering/timing assumptions. Native Unity hardware
execution remains pending.

## Native hardware run (2026-11-03)

Owner authorized temporary testing on the attached flue-monitor. Both added
Unity cases passed on ESP32-PICO-V3-02 revision 3.1, two cores, 2 MB PSRAM,
160 MHz CPU and active 800 ms IWDT: 32 tick/mode rounds per core and 100
20 ms timer-woken sleeps per core. No cases were ignored.

The first attempt passed the mode checks but failed Unity's teardown memory
check (4488 bytes). The test now waits for the worker to suspend before deleting
it; the rerun passes including teardown. This changes test cleanup only.

Exact test bin/ELF/map, exported sources, sdkconfig, UART and flash logs are in
`.cache/iwdt-hardware-test/monitor-run2/`. See `results.json` there for restoration
verification. Only the active application slot was written; its complete backup
was validated against the deployed 693379f6 image before testing.

These short tests exercise real sleep and register read-backs with the watchdog
running. They do not force the rare handler/transition overlap, measure masked
commit latency, prove APB-to-DRAM ordering, or replace a production soak.

Broader native hardware regression: 55 selected esp_system Unity cases passed
with active IWDT, including panic/hardware resets, IPC, PSRAM retention and sleep
stress. Four upstream ignored entries and one NVS-writing case were excluded.
This is one board/configuration; see [HARDWARE_RESULTS.md](HARDWARE_RESULTS.md)
for exact scope, exclusions and artifacts.
