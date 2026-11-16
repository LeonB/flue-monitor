#pragma once
#include <stdbool.h>
#include "sensors.h"
#include "settings.h"
#include "web_request.h"

void refill_notify_sample(const sensor_reading_t *reading);
void refill_notify_manual_event(const char *event);
// Runs on the existing Sheets network worker; never on the sensor/HTTP task.
void refill_notify_send_pending(const settings_t *settings);
void refill_notify_register(httpd_handle_t server);
