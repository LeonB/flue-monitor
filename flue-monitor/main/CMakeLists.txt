set(app_sources main.c sensors.c settings.c rest_api.c dashboard_auth.c ws_server.c sheets_logger.c status_led.c pagekite_tunnel.c memory_diagnostics.c)
idf_component_register(SRCS ${app_sources}
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES esp_event esp_netif esp_wifi nvs_flash wifi_setup captive_portal ota_server
                                     esp_http_server esp_http_client app_update mdns i2cdev mcp960x
                                     driver esp_pm esp_rom esp_timer esp-tls mbedtls led_strip
                       EMBED_FILES web_ui/fonts/caprasimo-400.woff2 web_ui/fonts/figtree-400.woff2
                                   web_ui/fonts/figtree-600.woff2 web_ui/fonts/figtree-700.woff2)

# Rebuild compressed payloads and cache tags whenever any served asset changes.
set(WEB_ASSET_HEADER "${CMAKE_CURRENT_BINARY_DIR}/web_assets_generated.h")
add_custom_command(OUTPUT "${WEB_ASSET_HEADER}"
                   COMMAND "${PYTHON}" "${CMAKE_CURRENT_LIST_DIR}/../tools/generate_web_assets.py" "${WEB_ASSET_HEADER}"
                   DEPENDS "${CMAKE_CURRENT_LIST_DIR}/../tools/generate_web_assets.py"
                           web_ui/flue-icon-stove.svg
                           web_ui/favicon.ico
                           web_ui/apple-touch-icon.png
                           web_ui/icon-192.png
                           web_ui/icon-512.png
                           web_ui/loading.html web_ui/service-worker.js
                           web_ui/site.webmanifest
                           web_ui/startup-640x1136.png
                           web_ui/startup-750x1334.png
                           web_ui/startup-1242x2208.png
                           web_ui/startup-1125x2436.png
                           web_ui/startup-828x1792.png
                           web_ui/startup-1242x2688.png
                           web_ui/startup-1170x2532.png
                           web_ui/startup-1179x2556.png
                           web_ui/startup-1206x2622.png
                           web_ui/startup-1284x2778.png
                           web_ui/startup-1290x2796.png
                           web_ui/startup-1320x2868.png
                           web_ui/startup-1260x2736.png
                           web_ui/startup-1080x2340.png
                           web_ui/dashboard.html web_ui/dashboard.js web_ui/dashboard.css
                           web_ui/burn-graph.js web_ui/vendor/uplot.min.js web_ui/vendor/uplot.min.css
                           "${CMAKE_CURRENT_LIST_DIR}/../../components/captive_portal/alpine.min.js"
                           "${CMAKE_CURRENT_LIST_DIR}/../../components/captive_portal/styles.css"
                           web_ui/fonts/caprasimo-400.woff2 web_ui/fonts/figtree-400.woff2
                           web_ui/fonts/figtree-600.woff2 web_ui/fonts/figtree-700.woff2
                   VERBATIM)
add_custom_target(web_asset_header DEPENDS "${WEB_ASSET_HEADER}")
add_dependencies(${COMPONENT_LIB} web_asset_header)
target_include_directories(${COMPONENT_LIB} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
