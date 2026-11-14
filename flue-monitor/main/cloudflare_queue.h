#pragma once

#include <stdint.h>
#include <string.h>
#include "cf_tunnel.h"

// Task-owned GET backlog. Keep the origin socket limit while absorbing the
// browser's initial asset burst. Stream headers remain owned by the library.
#define CLOUDFLARE_PENDING_GETS 16
#define CLOUDFLARE_QUEUE_TIMEOUT_US 10000000LL

typedef struct {
  cft_stream_t *stream;
  int64_t deadline_us;
  uint64_t ticket;
} cloudflare_pending_get_t;

static cloudflare_pending_get_t pending_gets[CLOUDFLARE_PENDING_GETS];
static uint64_t pending_ticket;

static cft_stream_t *pending_detach(cloudflare_pending_get_t *entry) {
  cft_stream_t *stream = entry->stream;
  entry->stream = NULL;
  const cft_stream_handlers_t empty = {0};
  cft_stream_set_handlers(stream, &empty, NULL);
  cft_stream_pause_body(stream, false);
  return stream;
}

static void pending_closed(cft_stream_t *stream, void *ctx, bool completed) {
  (void)completed;
  cloudflare_pending_get_t *entry = ctx;
  if (entry->stream == stream) entry->stream = NULL;
}

static void pending_body(cft_stream_t *stream, void *ctx, const uint8_t *body, size_t len) {
  (void)stream; (void)body;
  if (!len) return;
  cft_stream_respond(pending_detach(ctx), 400, "text/plain", "GET body not supported\n", 23);
}

static cloudflare_pending_get_t *pending_oldest(void) {
  cloudflare_pending_get_t *oldest = NULL;
  for (size_t i = 0; i < CLOUDFLARE_PENDING_GETS; i++)
    if (pending_gets[i].stream && (!oldest || pending_gets[i].ticket < oldest->ticket)) oldest = &pending_gets[i];
  return oldest;
}

static void proxy_get(cft_stream_t *stream) {
  if (cft_stream_proxy(stream, "http://127.0.0.1:80") < 0)
    cft_stream_respond(stream, 502, "text/plain", "Proxy unavailable\n", 18);
}

static void queue_get(cft_stream_t *stream, int64_t now_us) {
  if (!pending_oldest() && cft_stream_proxy_available(stream)) {
    proxy_get(stream);
    return;
  }
  for (size_t i = 0; i < CLOUDFLARE_PENDING_GETS; i++) {
    cloudflare_pending_get_t *entry = &pending_gets[i];
    if (entry->stream) continue;
    *entry = (cloudflare_pending_get_t){stream, now_us + CLOUDFLARE_QUEUE_TIMEOUT_US, ++pending_ticket};
    const cft_stream_handlers_t handlers = {.on_body = pending_body, .on_close = pending_closed};
    cft_stream_set_handlers(stream, &handlers, entry);
    cft_stream_pause_body(stream, true);
    return;
  }
  cft_stream_respond(stream, 503, "text/plain", "Proxy busy\n", 11);
}

static void pump_gets(int64_t now_us) {
  cloudflare_pending_get_t *entry;
  while ((entry = pending_oldest())) {
    if (now_us >= entry->deadline_us) {
      cft_stream_respond(pending_detach(entry), 503, "text/plain", "Proxy busy\n", 11);
      continue;
    }
    if (!cft_stream_proxy_available(entry->stream)) break;
    proxy_get(pending_detach(entry));
  }
}

// Call after freeing the tunnel, when every on_close callback has completed.
static void reset_gets(void) {
  memset(pending_gets, 0, sizeof pending_gets);
  pending_ticket = 0;
}
