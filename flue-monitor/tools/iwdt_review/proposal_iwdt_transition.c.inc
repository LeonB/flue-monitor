/* IWDT transition candidate v3. Not hardware-validated.
 * Handler bookkeeping is exported by the SHA-pinned generated highint_hdl.S.
 * A masked observation plus a fresh long deadline precedes mode publication.
 * Relies on the SDK handler's MEMW ordering of peripheral writes before its
 * final DRAM bookkeeping. Host tests do not establish silicon bus ordering.
 */
static bool s_flue_livelock_enabled = true;

extern volatile uint32_t _lx_intr_livelock_sync[2], _lx_intr_livelock_app, _lx_intr_livelock_pro;

/* Defensive software bound. While a handler is active we do NOT feed; the
 * hardware watchdog remains responsible for a stalled core. This is not a
 * promise that the caller can wait this long without a watchdog reset.
 */
#ifndef FLUE_IWDT_MAX_WAIT_CYCLES
#define FLUE_IWDT_MAX_WAIT_CYCLES (1u << 30)
#endif

/* With our core masked, observe both handler halves. A new expiry during
 * the initial observation/write is checked again after the fresh long feed.
 * The volatile loads are separate; this is not an atomic snapshot.
 */
static inline __attribute__((always_inline)) bool flue_iwdt_handler_idle(void)
{
    flue_iwdt_observe_barrier();
    bool idle = !flue_iwdt_interrupt_pending()
        && _lx_intr_livelock_app == 0 && _lx_intr_livelock_pro == 0
        && _lx_intr_livelock_sync[0] == 0 && _lx_intr_livelock_sync[1] == 0;
    flue_iwdt_observe_barrier();
    return idle;
}

/* Read-back detects rejected writes; it does not establish exclusive access
 * by itself. Exclusivity comes from the handler-idle checks and local mask.
 */
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

/* Tick path. In normal mode the original SDK feed operations; the flag only
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
