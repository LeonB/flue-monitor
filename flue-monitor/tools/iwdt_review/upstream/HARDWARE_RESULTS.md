# Native hardware regression results — 2026-11-03

ESP32-PICO-V3-02 rev3.1 (flue-monitor), two cores, 2 MB PSRAM, 160 MHz default
CPU frequency, active 800 ms IWDT and ECO3 cache-livelock workaround. ESP-IDF
v6.0.3 with the exported candidate patch; original production bootloader retained.

The existing pytest-embedded `run_all_single_board_cases(timeout=60)` runner
executed all non-ignored cases in this build except the NVS-writing time test.
Result: **55 passed, 0 failures, 0 errors, 0 runtime skips**, 91.49 seconds.
The four upstream menu entries marked ignore were not run.

This covers IWDT panic and hardware reset, task/RTC watchdogs, backtraces, IPC,
CPU stalls, light/deep sleep, PSRAM retention, timers and both new IWDT tests.

## Exclusions and limits

`check a time after wakeup from deep sleep` writes NVS and can erase it on an
initialization error. It was excluded to preserve production settings.
Upstream ignored entries:
- reset reason ESP_RST_POWERON
- reset reason ESP_RST_BROWNOUT after brownout event
- stack smashing protection
- light sleep duration is correct

This is one chip/configuration, not the complete multi-target ESP-IDF CI matrix.
The separate pytest UART-output assertions and stack-smash-specific runner were
not executed; UART cases above passed their Unity assertions only. There was
no deterministic race injection, long soak or hardware ordering proof.

## Artifacts and restoration

`.cache/iwdt-hardware-test/monitor-suite/` contains the runner adapter, complete
pytest log, menu inventory, JUnit XML, flash logs and restoration results. Exact
test image/source/config artifacts are in sibling `monitor-run2/`, SHA256
`c0d100234751fb22f3c4e9bf0e67e552211b7c6657258bbeb8aca27d9becaa39`.
Only app slot 0x20000 is written; the script restores its validated full backup
in a finally block. Restoration completed with esptool hash verification; boot confirmed original
ELF91bbafd37, MCP9601 and WiFi. results.json records restored=true and
restored_boot_verified=true. Monitoring remains paused.

The first two-case attempt exposed test-task cleanup timing (4488-byte leak).
Waiting for the worker to suspend before deleting it resolved that failure;
both the two-case rerun and complete selected suite pass with that test-only fix.

## Passed cases

- Test backtrace from abort
- Test backtrace from interrupt watchdog timeout
- Test backtrace with a ROM function
- Test esp_backtrace_print_all_tasks()
- Test blocking IPC function call
- Test ipc_task works with the priority of the caller's task
- Test multiple ipc_calls
- Test ipc_task can not wake up blocking task early
- Test ipc call nonblocking
- Test ipc call nonblocking when FreeRTOS Scheduler is suspended
- Test recursion IPC call
- interrupt watchdog mode survives tick feeds on both cores
- interrupt watchdog mode survives light sleep on both cores
- reset reason ESP_RST_DEEPSLEEP
- reset reason ESP_RST_PANIC after exception
- reset reason ESP_RST_PANIC after abort
- reset reason ESP_RST_SW after restart
- reset reason ESP_RST_SW after restart from APP CPU
- reset reason ESP_RST_INT_WDT after interrupt watchdog (panic)
- reset reason ESP_RST_INT_WDT after interrupt watchdog (hw)
- reset reason ESP_RST_TASK_WDT after task watchdog
- reset reason ESP_RST_WDT after RTC watchdog
- test printf using shared buffer stack
- Test effect of rtc clk calibration compensation on system time
- Task WDT task timeout
- Task WDT inactive when no task to watch
- Task WDT can be reconfigured
- Task WDT task feed
- Task WDT user timeout
- Task WDT user feed
- wake up from light sleep using timer
- light sleep stress test
- light sleep stress test with periodic esp_timer
- light sleep and frequency switching
- disable source trigger behavior
- Test PSRAM survives after lightsleep
- enter deep sleep on APP CPU and wake up using timer
- wake up from deep sleep using timer
- light sleep followed by deep sleep
- enter deep sleep more than once
- enter deep sleep after abort
- esp_sleep_set_console_uart_handling_mode parameter validation
- UART flush mode output verification
- UART suspend mode output verification
- UART discard mode output verification
- esp_rom_delay_us produces correct delay on CPUs
- vTaskDelay produces correct delay on CPUs
- Test ipc_isr blocking IPC function calls a ASM function
- Test ipc_isr blocking IPC function calls get_other_core_id
- Test ipc_isr exception in asm func leads to StoreProhibited not to Unhandled debug exception
- Test ipc_isr blocking IPC function calls get_cycle_count_other_cpu
- Test ipc_isr two tasks use IPC function calls
- Test stall other CPU safe
- Test nested stall other CPU release
- Test stall other CPU safe with callbacks

## Master-port validation

PR head fe161f61a333507ba2d3d074fd42c6eb052218ab, upstream base
0e6b480f858c69862ffb6001d96e9eef74599a6e, Xtensa GCC esp-16.1.0_20260609.
The complete native Unity application builds. An explicit hal/mwdt_periph.h
include was required because master removed the previous include supplying
TIMG_WDT_WKEY_VALUE; this is the only functional port fix after the earlier
merge. Existing CPU1-idle tick behavior is retained. All pre-commit hooks pass
without the earlier submodule-related exclusion.

56 selected native Unity cases passed in 92.75 seconds, zero failures/errors/
runtime skips. Same ESP32-PICO-V3-02 rev3.1, 2 MB PSRAM, 160 MHz default CPU,
800 ms active IWDT. The device's existing v6.0.3 bootloader was retained.
Four upstream-ignored entries and the NVS-writing time test were not run.
Separate UART-output/stack-smash pytest checks remain outside this run.

Exact image, ELF/map, sdkconfig, commit, JUnit, UART/flash logs and restoration
status: .cache/iwdt-master-test/monitor-suite/. Test image SHA256
496b7889777bffb3101906a2f1964cf8ea26289bc8d8605949b2a7eec350e70f.
Restoration hash verification passed, and the original ELF91bbafd37 boot,
MCP9601 and WiFi IP were confirmed; results.json records both restoration flags. No production v3
deployment or recorder restart is implied.
