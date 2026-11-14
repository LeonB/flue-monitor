# flue-monitor: the wood stove flue temperature sidecar (see ../CLAUDE.md),
# rewritten from ESPHome as plain ESP-IDF (this folder was flue-monitor-idf/
# during development, alongside the original ESPHome flue-monitor/, which has
# since been retired and removed). Boilerplate below matches Espressif's own
# project template exactly.
cmake_minimum_required(VERSION 3.16)

# wifi_setup/captive_portal/dns_server live in ../components/, shared with
# ../flue-display/ -- see ../CLAUDE.md's "Shared components" section.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../components")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(flue-monitor)
include(cmake/iwdt_transition.cmake)

# Keep the new protocol libraries within the existing OTA slots. LTO is scoped
# to task-context tunnel/HTTP2 code; SDK IRAM and watchdog objects are unchanged.
idf_component_get_property(cf_lib esp_cf_tunnel COMPONENT_LIB)
idf_component_get_property(h2_lib espressif__nghttp COMPONENT_LIB)
target_compile_options(${cf_lib} PRIVATE -flto)
target_compile_options(${h2_lib} PRIVATE -flto)
idf_build_get_property(app_elf EXECUTABLE)
target_link_options(${app_elf} PRIVATE -flto)
