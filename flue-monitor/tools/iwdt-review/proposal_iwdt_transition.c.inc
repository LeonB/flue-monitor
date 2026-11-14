/* PROPOSAL v3 -- NOT DEPLOYED.  Candidate replacement for cmake/iwdt_transition.c.inc.
 *
 * Needs, in tools/patch_iwdt_transition.py:
 *   - two extra PORT helpers (same style as flue_iwdt_stage0_ticks):
 *       flue_iwdt_write_protect_is_open(): REG_READ(TIMG_WDTWPROTECT_REG(1)) == TIMG_WDT_WKEY_VALUE
 *       flue_iwdt_stage1_ticks():          REG_READ(TIMG_WDTCONFIG3_REG(1))
 *   - the tick-hook replacement changed from flue_iwdt_update(false, true) to flue_iwdt_tick()
 *   - access to the handler's bookkeeping words _lx_intr_livelock_sync/app/pro, which
 *     highint_hdl.S keeps file-local (only counter/max are .global).  Either generate a
 *     project-local copy of highint_hdl.S with three `.global` lines added (SHA-pinned like
 *     the two C files), or address them relative to _lx_intr_livelock_max (they follow it
 *     contiguously in .data: max+4 sync[0], +8 sync[1], +12 app, +16 pro; verified with nm on
 *     the deployed ELF) with a build-time nm check.  The first is cleaner.
 *
 * Included in the SHA-checked ESP-IDF 6.0.3 int_wdt.c translation unit.
 */
static bool s_flue_livelock_enabled = true;

extern volatile uint32_t _lx_intr_livelock_sync[2], _lx_intr_livelock_app, _lx_intr_livelock_pro;

/* Bound on the whole transition in CPU cycles, NOT attempts.  Legitimate long
 * waits exist: a handler round takes ~2x its delay loop, and a CPU1 that missed
 * the sync[0] rendezvous (highint_hdl.S:394 vs :505-:527) is frozen until the
 * NEXT expiry re-enters the handler, which after our 1600-tick feed is 800 ms.
 * The bound therefore exceeds stage0+stage1 (2.4 s): 1<<30 cycles is ~4.5 s
 * @240 MHz.  It only exists to turn a state this code does not understand
 * into a visible abort instead of an endless loop. */
#ifndef FLUE_IWDT_MAX_WAIT_CYCLES
#define FLUE_IWDT_MAX_WAIT_CYCLES (1u << 30)
#endif

/* Caller holds rsil 5.  True iff no half of the livelock handler is in flight
 * on either core and no expiry is pending:
 *  - INT_RAW clear: CPU0's half has passed INT_CLR, or there was no expiry.
 *  - app == 0: CPU1 is not between its first entry and the end of its second
 *    entry.  The handler clears it at CPU1's exit, AFTER its stage0/stage1/feed
 *    writes (each followed by memw), so app == 0 also means those writes have
 *    landed.  pro == 0 and sync == {0,0}: both halves have exited.
 * A new entry needs a new expiry. */
static inline __attribute__((always_inline)) bool flue_iwdt_handler_idle(void)
{
    return !flue_iwdt_interrupt_pending()
        && _lx_intr_livelock_app == 0 && _lx_intr_livelock_pro == 0
        && _lx_intr_livelock_sync[0] == 0 && _lx_intr_livelock_sync[1] == 0;
}

/* Write stage0/stage1/feed and prove all three were accepted.  Caller holds
 * rsil 5 and s_iwdt_configure_lock.
 *  - WPROTECT still holding our key after the three writes => nobody closed it
 *    in between => the three writes were accepted.
 *  - stage0/stage1 read back AFTER our close: a foreign write that landed
 *    between ours and the close shows up; after the close nothing can land
 *    without a new open, i.e. a new handler entry. */
static bool ESP_SYSTEM_IRAM_ATTR flue_iwdt_write_stages(uint32_t stage0_ticks)
{
    wdt_hal_write_protect_disable(&iwdt_context);
    wdt_hal_config_stage(&iwdt_context, WDT_STAGE0, stage0_ticks, WDT_STAGE_ACTION_INT);
    wdt_hal_config_stage(&iwdt_context, WDT_STAGE1, IWDT_STAGE1_TIMEOUT_US, WDT_STAGE_ACTION_RESET_SYSTEM);
    wdt_hal_feed(&iwdt_context);
    bool accepted = flue_iwdt_write_protect_is_open();
    wdt_hal_write_protect_enable(&iwdt_context);
    return accepted
        && flue_iwdt_stage0_ticks() == stage0_ticks
        && flue_iwdt_stage1_ticks() == IWDT_STAGE1_TIMEOUT_US;
}

static void ESP_SYSTEM_IRAM_ATTR flue_iwdt_commit_mode(bool enable)
{
    uint32_t t0 = esp_cpu_get_cycle_count();
    while ((uint32_t)(esp_cpu_get_cycle_count() - t0) < FLUE_IWDT_MAX_WAIT_CYCLES) {
        unsigned ps = flue_iwdt_mask_high_interrupts();
        if (!flue_iwdt_handler_idle()) {
            /* A half is in flight on some core.  Do not feed and do not wait
             * with high interrupts masked: the round finishes by itself, and a
             * stalled rendezvous is completed by the next expiry. */
            flue_iwdt_restore_high_interrupts(ps);
            continue;
        }

        /* Step 1: long stage, fresh feed, handler mode unchanged.  No half is
         * in flight, so the only writer that can interfere is a half that
         * enters because of an expiry during these writes (stale counter). */
        if (!flue_iwdt_write_stages(IWDT_STAGE0_TIMEOUT_US)) {
            flue_iwdt_restore_high_interrupts(ps);
            continue;
        }

        /* Step 2: still idle?  A half that entered during step 1 is at least a
         * full delay loop (>= 480 cycles) away from any register write, and it
         * shows up here as INT_RAW/app/sync/pro. */
        if (!flue_iwdt_handler_idle()) {
            flue_iwdt_restore_high_interrupts(ps);
            continue;
        }

        /* Step 3: commit.  Disable: max=0 while stage0 is already 1600 and fed
         * < 100 cycles ago; WPROTECT stays closed, so a late foreign stage write
         * cannot be accepted even if one existed.  Enable: max=39 first, then
         * the short stage (the reverse combination is harmless). */
        bool ok;
        if (enable) {
            esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);
            ok = flue_iwdt_write_stages(esp_int_wdt_livelock_get_feed_stage0_ticks());
        } else {
            esp_int_wdt_reset_livelock_params();
            ok = !flue_iwdt_write_protect_is_open()
              && flue_iwdt_stage0_ticks() == IWDT_STAGE0_TIMEOUT_US
              && flue_iwdt_stage1_ticks() == IWDT_STAGE1_TIMEOUT_US;
        }
        flue_iwdt_restore_high_interrupts(ps);
        if (!ok) {
            /* Cannot happen per the model.  If it does, crash visibly instead
             * of sleeping with an unknown watchdog state. */
            abort();
        }
        return;
    }
    abort();
}

void ESP_SYSTEM_IRAM_ATTR esp_int_wdt_set_livelock_mode(bool enable)
{
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    if (soc_has_cache_lock_bug()) {
        flue_iwdt_commit_mode(enable);
        s_flue_livelock_enabled = enable;
    } else {
        reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
    }
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}

/* Tick path.  In normal mode byte-for-byte the original SDK tick; the flag only
 * stops a tick during sleep mode from writing max=39/stage0=40 back.  No
 * masking: it never changes max in a way the handler cares about (39 -> 39),
 * and the lock orders it against a mode change. */
static void ESP_SYSTEM_IRAM_ATTR flue_iwdt_tick(void)
{
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    if (soc_has_cache_lock_bug() && s_flue_livelock_enabled) {
        esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);
        reconfigure_ticks(esp_int_wdt_livelock_get_feed_stage0_ticks(), IWDT_STAGE1_TIMEOUT_US);
    } else {
        reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
    }
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}
