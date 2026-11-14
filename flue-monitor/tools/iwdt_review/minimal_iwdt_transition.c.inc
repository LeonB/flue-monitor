/* Review alternative only: reorder disable and retain the mode across ticks.
 * Uses the existing C lock, but adds no assembly-handler exclusion.
 */
static bool s_flue_livelock_enabled = true;

void ESP_SYSTEM_IRAM_ATTR esp_int_wdt_set_livelock_mode(bool enable)
{
    portENTER_CRITICAL_SAFE(&s_iwdt_configure_lock);
    if (soc_has_cache_lock_bug()) {
        if (enable) {
            esp_int_wdt_set_livelock_params(CONFIG_ESP_INT_WDT_TIMEOUT_MS);
            reconfigure_ticks(esp_int_wdt_livelock_get_feed_stage0_ticks(), IWDT_STAGE1_TIMEOUT_US);
        } else {
            reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
            esp_int_wdt_reset_livelock_params();
        }
        s_flue_livelock_enabled = enable;
    } else {
        reconfigure_ticks(IWDT_STAGE0_TIMEOUT_US, IWDT_STAGE1_TIMEOUT_US);
    }
    portEXIT_CRITICAL_SAFE(&s_iwdt_configure_lock);
}

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
