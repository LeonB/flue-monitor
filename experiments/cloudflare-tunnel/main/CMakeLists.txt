idf_component_register(SRCS "main.c"
    PRIV_REQUIRES esp_wifi esp_event esp_netif esp_timer esp_hw_support heap nvs_flash lwip
    REQUIRES esp_cf_tunnel)
