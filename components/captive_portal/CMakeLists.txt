# IDF 6 moved cJSON to the component registry; the display still uses IDF 5.
if(IDF_VERSION_MAJOR GREATER_EQUAL 6)
    set(portal_json_component espressif__cjson)
else()
    set(portal_json_component json)
endif()
idf_component_register(SRCS captive_portal.c compressed_assets.c
                       INCLUDE_DIRS include
                       PRIV_REQUIRES esp_wifi esp_netif esp_event esp_http_server esp_rom ${portal_json_component} dns_server wifi_setup)
set(PORTAL_ASSET_HEADER "${CMAKE_CURRENT_BINARY_DIR}/portal_assets_generated.h")
add_custom_command(OUTPUT "${PORTAL_ASSET_HEADER}"
                   COMMAND "${PYTHON}" "${CMAKE_CURRENT_LIST_DIR}/generate_assets.py" "${PORTAL_ASSET_HEADER}"
                   DEPENDS generate_assets.py root.html styles.css alpine.min.js
                   VERBATIM)
add_custom_target(portal_asset_header DEPENDS "${PORTAL_ASSET_HEADER}")
add_dependencies(${COMPONENT_LIB} portal_asset_header)
target_include_directories(${COMPONENT_LIB} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
