I encountered this while working on a wood-stove flue temperature monitor built with ESP-IDF. The device uses an ESP32-PICO-V3-02 with PSRAM and automatic light sleep, and was experiencing intermittent interrupt-watchdog resets during normal operation. Capturing a core dump led me to investigate the transition between the cache-livelock recovery mode and the longer watchdog timeout used for light sleep.

The captured crash reported:

```text
Guru Meditation Error: Core  0 panic'ed (Interrupt wdt timeout on CPU0).
```

Disabling the ESP32 cache livelock workaround before light sleep clears the software recovery budget before extending the watchdog timeout. An interrupt in that window can observe a zero budget with the short timeout still active and trigger an interrupt-watchdog panic.

A captured CPU0 interrupt-watchdog panic places execution at `wdt_hal_write_protect_disable`, after the recovery budget was cleared and before the longer timeout was configured. This is consistent with the race; the dump does not contain the watchdog registers, and the race has not been reproduced deterministically on hardware.

Relevant symbolized frames (ESP-IDF v6.0.3):

```text
wdt_hal_write_protect_disable
reconfigure_ticks(stage0_ticks=1600, stage1_ticks=3200)
esp_int_wdt_reconfigure_ticks
esp_int_wdt_livelock_workaround(enable=false)
esp_light_sleep_start
```

Serialize mode transitions with tick feeds. With local high interrupts masked, check `INT_RAW` and both handlers' `app/pro/sync` state before changing the budget and timeout. `INT_RAW` alone is insufficient because CPU0 clears it before CPU1 finishes its delayed watchdog writes. CPU1 can also close the shared WPROTECT register while CPU0 is configuring the timeout; the C spinlock does not exclude that assembly handler. Export the existing state symbols without changing handler instructions, verify register writes, and keep tick feeds in the selected mode.

While a handler is active, restore high interrupts and retry without feeding. A stalled handler can therefore still trigger the watchdog. Abort if the transition exceeds `1 << 30` CPU cycles or the final register verification fails. Observing handler completion relies on `memw` ordering peripheral writes before the handler publishes idle state in DRAM. The existing assembly rendezvous protocol is unchanged.

Adds two tests to `esp_system_unity_tests`: mode retention across tick feeds and repeated timer-woken light sleep, both exercised on each core. The sleep test requires 100 successful cycles within 1,000 attempts per core and checks that the watchdog mode is restored after `ESP_ERR_SLEEP_REJECT`; other errors fail the test.

Validation at commit `f90a92f1044022870ad151240805e246d8080014`, based on `master` commit `0e6b480f858c69862ffb6001d96e9eef74599a6e`:

- The complete native `esp_system_unity_tests` application builds with the required Xtensa GCC 16.1.0 toolchain.
- **56 selected native Unity tests passed** on ESP32-PICO-V3-02 rev3.1 with two cores, 2 MB PSRAM, 160 MHz default CPU frequency and active 800 ms IWDT. Zero failures, errors or runtime skips. Coverage includes IWDT panic/hardware resets, task/RTC watchdogs, IPC/CPU stalls, PSRAM retention and light/deep sleep.
- The new tests passed 32 mode-transition rounds per core. The updated light-sleep test passed on both cores: CPU0 — 100 attempts, 100 successful cycles, 0 rejections; CPU1 — 100 attempts, 100 successful cycles, 0 rejections.
- Official pre-commit checks passed. Extracted C functions also passed a supplementary external ASan/UBSan host harness, including the upstream CPU1-idle tick condition; that harness is not part of this PR.
- Hardware coverage is limited to this board/configuration, using its existing v6.0.3 bootloader. The tests do not deterministically inject the transition race.

AI assistance was used in development and testing.

<!-- CURSOR_SUMMARY -->
---

> [!NOTE]
> **High Risk**
> Changes IRAM-critical interrupt-watchdog and ECO3 livelock coordination used on every tick feed and light sleep; a bug could cause spurious resets or failed sleep transitions.
>
> **Overview**
> Fixes an intermittent **interrupt watchdog panic** on ESP32 ECO3 when turning off the cache-livelock recovery path before light sleep: the recovery budget could be cleared while the short stage-0 timeout was still active, so a WDT interrupt could fire during `reconfigure_ticks`.
>
> **`esp_int_wdt_set_livelock_mode`** replaces the old “reset params + reconfigure ticks” sequence in **`esp_int_wdt_livelock_workaround`**. Transitions run under the existing configure lock, with high interrupts masked locally, **`INT_RAW` plus `_lx_intr_livelock_sync` / `_app` / `_pro`** used to wait for both handler halves to finish (without feeding while a handler is active), then a full timeout is installed before publishing the new budget and short timeout. Register writes are read back; failed verification or excessive wait **`abort()`s**. **`s_livelock_enabled`** and new **`iwdt_tick()`** keep tick feeds aligned with the selected mode.
>
> Assembly only **exports** the livelock bookkeeping symbols for C; handler logic is unchanged. Unity tests on each core cover mode toggling with tick feeds and repeated timer-woken light sleep.
>
> <sup>Reviewed by [Cursor Bugbot](https://cursor.com/bugbot) for commit c4fedc7a07f741a40de829b7eb4e7f27d5242714. Bugbot is set up for automated code reviews on this repo. Configure [here](https://www.cursor.com/dashboard/bugbot).</sup>
<!-- /CURSOR_SUMMARY -->
