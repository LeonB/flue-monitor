#pragma once
#include <stdbool.h>
#include "esp_http_server.h"
// Registers authenticated GET/POST /api/bosch and starts the read-only worker.
void bosch_client_start(httpd_handle_t server);

// Snapshot only; never performs cloud I/O. False means absent, failed or stale.
bool bosch_client_get_temperature(double *temperature_c);
