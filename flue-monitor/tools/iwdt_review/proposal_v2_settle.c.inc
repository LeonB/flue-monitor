/* PROPOSAL v3 -- NOT DEPLOYED.  Candidate replacement for cmake/iwdt_transition.c.inc.
 *
 * Needs two extra PORT helpers in tools/patch_iwdt_transition.py (same style as
 * flue_iwdt_stage0_ticks):
 *   flue_iwdt_write_protect_is_open(): REG_READ(TIMG_WDTWPROTECT_REG(1)) == TIMG_WDT_WKEY_VALUE
 *   flue_iwdt_stage1_ticks():          REG_READ(TIMG_WDTCONFIG3_REG(1))
 * and the tick-hook replacement changed from flue_iwdt_update(false, true) to flue_iwdt_tick().
 *
 * Included in the SHA-checked ESP-IDF 6.0.3 int_wdt.c translation unit.
 */
static bool s_flue_livelock_enabled = true;

/* How long we let a handler half that was already past INT_CLR finish its
 * register writes before we look a second time.  Availability assumption, not
 * a safety assumption: if it is too short the commit check below aborts
 * visibly, it never leaves a silent wrong state. */
#ifndef FLUE_IWDT_SETTLE_CYCLES
#define FLUE_IWDT_SETTLE_CYCLES   8000u
#endif
/* Bound on the whole transition in CPU cycles, NOT attempts.  Two legitimate
 * long waits exist: (a) a pending TG1 interrupt stays raw for ~2x the
 * handler's delay loop while CPU0's half waits to remap CPU1's interrupt;
 * (b) if CPU1 misses the sync[0] rendezvous (highint_hdl.S:394 vs :505-:527)
 * it is frozen until the NEXT expiry re-enters the handler, which after our
 * 1600-tick feed is 800 ms.  Every loop iteration feeds, so this bound is the
 * only thing that stops us from feeding forever; it must therefore exceed
 * stage0+stage1 (2.4 s) so a self-healed freeze is never turned into an
 * abort.  1<<30 cycles is ~4.5 s @240 MHz / ~13 s @80 MHz. */
#ifndef FLUE_IWDT_MAX_WAIT_CYCLES
#define FLUE_IWDT_MAX_WAIT_CYCLES (1u << 30)
#endif

static inline __attribute__((always_inline)) void flue_iwdt_settle(void)
{
    uint32_t start = esp_cpu_get_cycle_count();
    while ((uint32_t)(esp_cpu_get_cycle_count() - start) < FLUE_IWDT_SETTLE_CYCLES) {
    }
}

/* Caller holds rsil 5. */
static inline __attribute__((always_inline)) bool flue_iwdt_quiescent(void)
{
    bool pending = flue_iwdt_interrupt_pending();
    uint32_t stage0 = flue_iwdt_stage0_ticks();
    return !pending && stage0 == IWDT_STAGE0_TIMEOUT_US;
}

/* Write stage0/stage1/feed and prove all three were accepted.  Caller holds
 * rsil 5 and s_iwdt_configure_lock, so the only other writer is the other
 * core's handler half, which can only close WPROTECT or write the stages.
 *  - WPROTECT still holding our key after the three writes => nobody closed it
 *    in between => the three writes were accepted (someone else opening it
 *    does not block us).
 *  - stage0/stage1 read back AFTER our close: a foreign stage write that landed
 *    between our write and our close shows up here, and after the close no
 *    write can land without a new open, which needs a new handler entry.
 *  - FEED cannot be read back; if a foreign close blocked only our feed, the
 *    foreign half fed a few cycles earlier (its feed precedes its close), and
 *    the stages were already ours, so the counter is fresh anyway. */
static bool ESP_SYSTEM_IRAM_ATTR flue_iwdt_write_mode(uint32_t stage0_ticks)
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
        /* Old handler mode, long stage, fresh feed. */
        reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);

        unsigned ps = flue_iwdt_mask_high_interrupts();
        bool ok = flue_iwdt_quiescent();
        flue_iwdt_restore_high_interrupts(ps);
        if (!ok) {
            continue;
        }

        /* A handler half that was already past INT_CLR writes the short stage
         * within this window and is caught by the second look. */
        flue_iwdt_settle();

        ps = flue_iwdt_mask_high_interrupts();
        if (!flue_iwdt_quiescent()) {
            flue_iwdt_restore_high_interrupts(ps);
            continue;
        }

        /* Commit.  Disable: stage0 is already 1600 (verified above), so writing
         * max=0 first never creates the "short stage, no budget" combination.
         * Enable: max=39 first, then the short stage; the reverse combination
         * (long stage, budget) is harmless. */
        uint32_t target;
        if (enable) {
            esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);
            target = esp_int_wdt_livelock_get_feed_stage0_ticks();
        } else {
            esp_int_wdt_reset_livelock_params();
            target = IWDT_STAGE0_TIMEOUT_US;
        }
        bool committed = flue_iwdt_write_mode(target);
        flue_iwdt_restore_high_interrupts(ps);
        if (!committed) {
            /* The model says this cannot happen after the second look.  If it
             * does, the model is wrong; crash visibly rather than sleep with
             * an unknown watchdog state. */
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
 * masking needed: it never changes max in a way the handler cares about
 * (39 -> 39), and the lock orders it against a mode change. */
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
