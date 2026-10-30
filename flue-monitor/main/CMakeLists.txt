set(app_sources main.c sensors.c settings.c rest_api.c dashboard_auth.c ws_server.c sheets_logger.c status_led.c pagekite_tunnel.c memory_diagnostics.c)
if(CONFIG_FLUE_DIAG_TRACE_SDK)
    list(APPEND app_sources sleep_diagnostics.c)
endif()
idf_component_register(SRCS ${app_sources}
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES esp_event esp_netif esp_wifi nvs_flash wifi_setup captive_portal ota_server
                                     esp_http_server esp_http_client app_update mdns i2cdev mcp960x
                                     driver esp_pm esp_rom esp_timer json esp-tls mbedtls led_strip
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

# Only explicit diagnostic builds replace SDK sources or wrap RTC sleep entry.
if(CONFIG_FLUE_DIAG_TRACE_SDK)
# Diagnostic wrapper around the ESP32 RTC sleep entry, without changing SDK files.
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=rtc_sleep_start")

# Temporary detailed trace: build a local copy with IRAM-safe breadcrumbs.
set(SLEEP_TRACE_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/../tools/trace_sleep_sdk.py")
# Preserve the basename: ESP-IDF linker fragments select sleep_modes by
# object name to place esp_light_sleep_start and related code in IRAM.
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/sleep_trace")
set(SLEEP_TRACE_SOURCE "${CMAKE_CURRENT_BINARY_DIR}/sleep_trace/sleep_modes.c")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${SLEEP_TRACE_SCRIPT}")
execute_process(COMMAND "${PYTHON}" "${SLEEP_TRACE_SCRIPT}"
                "${IDF_PATH}/components/esp_hw_support/sleep_modes.c" "${SLEEP_TRACE_SOURCE}"
                RESULT_VARIABLE sleep_trace_result)
if(NOT sleep_trace_result EQUAL 0)
    message(FATAL_ERROR "Sleep trace source guards failed; review SDK source")
endif()
idf_component_get_property(hw_support_lib esp_hw_support COMPONENT_LIB)
get_target_property(hw_support_sources ${hw_support_lib} SOURCES)
set(sleep_trace_replaced FALSE)
foreach(hw_source IN LISTS hw_support_sources)
    if(hw_source MATCHES "(^|/)sleep_modes\\.c$")
        list(REMOVE_ITEM hw_support_sources "${hw_source}")
        set(sleep_trace_replaced TRUE)
    endif()
endforeach()
if(NOT sleep_trace_replaced)
    message(FATAL_ERROR "Original sleep_modes.c not found for temporary tracing")
endif()
set_property(TARGET ${hw_support_lib} PROPERTY SOURCES "${hw_support_sources}")
target_sources(${hw_support_lib} PRIVATE "${SLEEP_TRACE_SOURCE}")

set(CLOCK_TRACE_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/../tools/trace_rtc_clock_sdk.py")
set(CLOCK_TRACE_SOURCE "${CMAKE_CURRENT_BINARY_DIR}/sleep_trace/rtc_clk.c")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CLOCK_TRACE_SCRIPT}")
execute_process(COMMAND "${PYTHON}" "${CLOCK_TRACE_SCRIPT}"
                "${IDF_PATH}/components/esp_hw_support/port/esp32/rtc_clk.c" "${CLOCK_TRACE_SOURCE}"
                RESULT_VARIABLE clock_trace_result)
if(NOT clock_trace_result EQUAL 0)
    message(FATAL_ERROR "RTC clock trace guards failed; review SDK source")
endif()
get_target_property(hw_support_sources ${hw_support_lib} SOURCES)
set(clock_trace_replaced FALSE)
foreach(hw_source IN LISTS hw_support_sources)
    if(hw_source MATCHES "(^|/)rtc_clk\\.c$")
        list(REMOVE_ITEM hw_support_sources "${hw_source}")
        set(clock_trace_replaced TRUE)
    endif()
endforeach()
if(NOT clock_trace_replaced)
    message(FATAL_ERROR "Original rtc_clk.c not found for temporary tracing")
endif()
set_property(TARGET ${hw_support_lib} PROPERTY SOURCES "${hw_support_sources}")
target_sources(${hw_support_lib} PRIVATE "${CLOCK_TRACE_SOURCE}")
endif()

include("${CMAKE_CURRENT_LIST_DIR}/../cmake/sleep_livelock_backport.cmake")
