/* Included in the SHA-checked ESP-IDF 6.0.3 int_wdt.c translation unit.
 * Keep the level-4/5 livelock handler enabled while acquiring the lock and
 * draining its interrupt: that handler rendezvous with BOTH CPUs.
 */
static bool s_flue_livelock_enabled = true;

static void ESP_SYSTEM_IRAM_ATTR flue_iwdt_update(bool change_mode, bool enable)
{
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    if (!change_mode) {
        enable = s_flue_livelock_enabled;
    }
    if (!soc_has_cache_lock_bug()) {
        reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
    } else {
        for (;;) {
            /* Retain the OLD handler mode until the short deadline is gone.
             * An interrupt may preempt these writes and restore the 20-ms
             * stage; its HAL write-protection changes can also interrupt us.
             * Validate the resulting hardware state below, not just our intent.
             */
            reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
            unsigned saved_ps = flue_iwdt_mask_high_interrupts();

            /* Order matters: pending FIRST, stage length SECOND. The other
             * CPU's recovery handler writes the short stage before clearing
             * pending. Never clear pending here or wait with high IRQs masked.
             */
            bool pending = flue_iwdt_interrupt_pending();
            uint32_t stage0 = flue_iwdt_stage0_ticks();
            if (pending || stage0 != IWDT_STAGE0_TIMEOUT_US) {
                flue_iwdt_restore_high_interrupts(saved_ps);
                continue;
            }

            /* No old IRQ is pending, and the hardware now has the long
             * deadline. The bounded IRAM-only commit below takes far less
             * than that deadline; the shared lock excludes other C writers.
             * Do not add blocking calls, flash accesses, or locks here.
             */
            if (enable) {
                esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);
            } else {
                esp_int_wdt_reset_livelock_params();
            }
            reconfigure_ticks(enable ? esp_int_wdt_livelock_get_feed_stage0_ticks()
                                     : IWDT_STAGE0_TIMEOUT_US,
                              IWDT_STAGE1_TIMEOUT_US);
            flue_iwdt_restore_high_interrupts(saved_ps);
            break;
        }
    }
    s_flue_livelock_enabled = enable;
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}

void ESP_SYSTEM_IRAM_ATTR esp_int_wdt_set_livelock_mode(bool enable)
{
    flue_iwdt_update(true, enable);
}
