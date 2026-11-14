#pragma once
#include <stdint.h>
#include "sdkconfig.h"

typedef enum {
    FLUE_EVT_BOOT = 1, FLUE_EVT_WIFI, FLUE_EVT_SENSOR_BEGIN, FLUE_EVT_SENSOR_END,
    FLUE_EVT_SHEETS_BEGIN, FLUE_EVT_SHEETS_END, FLUE_EVT_BOSCH_BEGIN, FLUE_EVT_BOSCH_END,
    FLUE_EVT_PAGEKITE_CONNECT, FLUE_EVT_PAGEKITE_READY, FLUE_EVT_PAGEKITE_ERROR,
    FLUE_EVT_NVS_BEGIN, FLUE_EVT_NVS_END, FLUE_EVT_OTA_BEGIN, FLUE_EVT_OTA_END,
    FLUE_EVT_ALLOC_FAIL_INTERNAL, FLUE_EVT_ALLOC_FAIL_PSRAM,
    FLUE_EVT_INTERNAL_FREE, FLUE_EVT_PSRAM_FREE, FLUE_EVT_TEST_READY, FLUE_EVT_TEST_CRASH,
    FLUE_EVT_SLEEP_BASE = 0x100,
} flue_event_t;

typedef struct {
    uint32_t sequence; // committed last; zero means incomplete
    uint32_t clock; // low microseconds, or CPU cycles when flags bit 0 is set
    uint16_t event;
    uint8_t core, flags;
    uint32_t value; // numeric status/size only; never credentials or payloads
} flue_record_t;
_Static_assert(sizeof(flue_record_t) == 16, "Recorder ABI must remain 16 bytes");

typedef struct {
    uint32_t magic, version;
    uint32_t heads[2][2]; // per core, operational/sleep bank
    flue_record_t operations[2][96];
    flue_record_t sleep[2][32];
} flue_recorder_t;

#if CONFIG_FLUE_DIAG_RECORDER
void flight_recorder_init(void);
void flue_trace_record(uint16_t event, uint32_t value);
void flight_recorder_test_start(void);
#define FLUE_TRACE(name, value) flue_trace_record(FLUE_EVT_##name, (uint32_t)(value))
#else
static inline void flight_recorder_init(void) {}
static inline void flight_recorder_test_start(void) {}
#define FLUE_TRACE(name, value) ((void)0)
#endif
