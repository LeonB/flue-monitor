#include "flight_recorder.h"
#if CONFIG_FLUE_DIAG_RECORDER && CONFIG_FLUE_DIAG_CRASH_TEST
#include <stdlib.h>
#include <string.h>
#include "driver/uart.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// Only present in the explicit --self-test build. No HTTP crash endpoint,
// automatic crash, persistent setting, or alteration to saved credentials.
COREDUMP_DRAM_ATTR volatile struct {
    uint32_t magic, seed, size;
    uint8_t *internal, *psram;
    volatile uint32_t *stack;
} flue_test_state;

// IDF6.0.3 invokes this callback while multi_heap_walk owns the heap lock.
// Deliberately stop servicing interrupts there to test panic capture with a
// held heap lock. Never present outside the explicit self-test image.
static bool IRAM_ATTR __attribute__((noreturn)) watchdog_with_heap_locked(walker_heap_into_t heap,
                                               walker_block_info_t block, void *arg) {
    (void)heap; (void)block; (void)arg;
    FLUE_TRACE(TEST_CRASH,0x43524153);
    portDISABLE_INTERRUPTS();
    for (;;) __asm__ volatile("nop");
}

static void __attribute__((noinline,noreturn)) controlled_crash(bool watchdog) {
    volatile uint32_t stack_marker[4]={0x53544143,0x4b544553,0x54524143,0x454f4b21};
    flue_test_state.magic=0x46545331;
    flue_test_state.seed=0x6d;
    flue_test_state.size=256;
    flue_test_state.internal=heap_caps_malloc(256,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    flue_test_state.psram=heap_caps_malloc(256,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if (!flue_test_state.internal || !flue_test_state.psram) {
        ESP_LOGE("flight_test","Cannot allocate verification buffers; test cancelled");
        free(flue_test_state.internal); free(flue_test_state.psram);
        flue_test_state.internal=NULL;flue_test_state.psram=NULL;
        vTaskDelete(NULL);
        abort(); // unreachable after deleting the current task
    }
    for (unsigned i=0;i<256;i++) {
        flue_test_state.internal[i]=(uint8_t)(i*17+flue_test_state.seed);
        flue_test_state.psram[i]=(uint8_t)(i*29+(flue_test_state.seed^0xa5));
    }
    flue_test_state.stack=stack_marker;
    for (unsigned i=0;i<300;i++) FLUE_TRACE(TEST_READY,i);
    FLUE_TRACE(TEST_CRASH,0x43524153);
    ESP_LOGW("flight_test","CONTROLLED_CRASH mode=%s internal=%p psram=%p stack=%p size=256",
             watchdog ? "IWDT_HEAP_LOCK" : "ABORT",
             flue_test_state.internal,flue_test_state.psram,(void *)stack_marker);
    // Publish the stack address and keep volatile markers live until abort.
    __asm__ volatile("" : : "r"(stack_marker) : "memory");
    if (watchdog) heap_caps_walk(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT,
                                watchdog_with_heap_locked,NULL);
    abort();
}

static void command_task(void *unused) {
    (void)unused;
    char input[48];size_t used=0;
    ESP_LOGI("flight_test","USB self-test armed; send FLUE_DIAG_CRASH followed by newline");
    for (;;) {
        uint8_t ch;
        if (uart_read_bytes(UART_NUM_0,&ch,1,pdMS_TO_TICKS(250))!=1) continue;
        if (ch=='\n' || ch=='\r') {
            input[used]=0;
            if (!strcmp(input,"FLUE_DIAG_CRASH")) controlled_crash(false);
            if (!strcmp(input,"FLUE_DIAG_WDT")) controlled_crash(true);
            used=0;
        } else if (used<sizeof input-1) input[used++]=ch;
        else used=0;
    }
}

void flight_recorder_test_start(void) {
    esp_err_t err=uart_driver_install(UART_NUM_0,256,0,0,NULL,0);
    if (err!=ESP_OK) { ESP_LOGE("flight_test","USB input unavailable: %d",err);return; }
    if (xTaskCreate(command_task,"flight_test",4096,NULL,1,NULL)!=pdPASS)
        ESP_LOGE("flight_test","USB self-test task unavailable");
}
#endif
