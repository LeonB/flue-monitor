# ESP32-specific, reviewed against the exact 6.0.3 sources. Keep the SDK intact.
if(CONFIG_IDF_TARGET_ESP32 AND CONFIG_ESP_INT_WDT AND CONFIG_ESP32_ECO3_CACHE_LOCK_FIX)
    set(iwdt_patch_dir "${CMAKE_CURRENT_LIST_DIR}")
    set(iwdt_generated "${CMAKE_BINARY_DIR}/iwdt-transition")
    set(iwdt_generator "${iwdt_patch_dir}/../tools/patch_iwdt_transition.py")
    execute_process(COMMAND "${PYTHON}" "${iwdt_generator}"
                            --idf "$ENV{IDF_PATH}" --output "${iwdt_generated}"
                    RESULT_VARIABLE iwdt_patch_result)
    if(NOT iwdt_patch_result EQUAL 0)
        message(FATAL_ERROR "IWDT transition patch rejected this SDK")
    endif()
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
        "${iwdt_generator}" "${iwdt_patch_dir}/iwdt_transition.c.inc"
        "$ENV{IDF_PATH}/components/esp_system/int_wdt.c"
        "$ENV{IDF_PATH}/components/esp_system/port/soc/esp32/eco3_livelock_workaround.c"
        "$ENV{IDF_PATH}/components/esp_system/port/soc/esp32/highint_hdl.S")
    idf_component_get_property(iwdt_system_lib esp_system COMPONENT_LIB)
    get_target_property(iwdt_sources ${iwdt_system_lib} SOURCES)
    set(iwdt_replaced 0)
    set(iwdt_new_sources "")
    foreach(iwdt_source IN LISTS iwdt_sources)
        if(iwdt_source MATCHES "(^|/)(int_wdt|eco3_livelock_workaround)\\.c$" OR
           iwdt_source MATCHES "(^|/)highint_hdl\\.S$")
            get_filename_component(iwdt_basename "${iwdt_source}" NAME)
            list(APPEND iwdt_new_sources "${iwdt_generated}/${iwdt_basename}")
            math(EXPR iwdt_replaced "${iwdt_replaced} + 1")
        else()
            list(APPEND iwdt_new_sources "${iwdt_source}")
        endif()
    endforeach()
    if(NOT iwdt_replaced EQUAL 3)
        message(FATAL_ERROR "Expected exactly three SDK source replacements for IWDT")
    endif()
    set_property(TARGET ${iwdt_system_lib} PROPERTY SOURCES "${iwdt_new_sources}")
endif()
