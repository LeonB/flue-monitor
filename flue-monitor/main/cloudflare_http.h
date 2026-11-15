#pragma once
#include "cf_tunnel.h"
#include <stdint.h>

// Tunnel-task callbacks. Application handlers are queued onto the HTTP task.
void cloudflare_http_request(cft_stream_t *stream, const cft_request_t *request, int64_t now_us);
void cloudflare_http_poll(int64_t now_us);
uint32_t cloudflare_http_wait_ms(void *arg);
