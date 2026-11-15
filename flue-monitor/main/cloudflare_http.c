#include "cloudflare_http.h"
#include "rest_api.h"
#include "web_request.h"
#include "buffer_memory.h"
#include "miniz.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#define DIRECT_REQUESTS 16
#define DIRECT_TIMEOUT_US 10000000LL
#define DIRECT_HEADERS 6
#define DIRECT_CHUNK 512

typedef struct {
  tinfl_decompressor inflater;
  unsigned char dictionary[TINFL_LZ_DICT_SIZE];
  size_t consumed, available, sent, produced;
  tinfl_status status;
} decoder_t;

// ESP32 S32C1I atomics require internal memory. Payloads and response metadata
// remain in PSRAM; only these eight bytes per request need internal RAM.
typedef struct {
  atomic_uint refs;
  atomic_bool done, cancelled;
} request_control_t;

typedef struct {
  request_control_t *control;
  cft_stream_t *stream;                 // Accessed only on the tunnel task.
  size_t slot, received, sent;
  int64_t deadline;
  uint64_t ticket;
  bool body_done, dispatched, started, ended;
  char *storage;
  size_t storage_size;
  web_header_t headers[DIRECT_HEADERS];
  web_request_t request;
  web_response_t response;
  decoder_t *decoder;
} direct_request_t;

static direct_request_t *pending[DIRECT_REQUESTS];
static uint64_t next_ticket;
// One queued handler at a time avoids filling HTTPD's control socket and keeps
// all mutable session/settings state serialized with native LAN requests.
static atomic_bool http_busy;

uint32_t cloudflare_http_wait_ms(void *arg) {
  (void)arg;
  // HTTPD does not write to a loopback socket anymore. Bound response handoff
  // latency while work is pending, retaining the normal idle/sleep interval.
  for (size_t i = 0; i < DIRECT_REQUESTS; i++)
    if (pending[i] && pending[i]->body_done && !pending[i]->started) return 5;
  return 0;
}

static void release_request(direct_request_t *r) {
  if (atomic_fetch_sub(&r->control->refs, 1) != 1) return;
  web_response_clear(&r->response);
  if (r->storage) memset(r->storage, 0, r->storage_size);
  free(r->storage);
  free(r->decoder);
  free(r->control);
  free(r);
}

static void closed(cft_stream_t *stream, void *ctx, bool completed) {
  (void)stream; (void)completed;
  direct_request_t *r = ctx;
  pending[r->slot] = NULL;
  atomic_store(&r->control->cancelled, true);
  // The worker owns its own reference, even if the entire tunnel is freed.
  release_request(r);
}

static void reject(direct_request_t *r, int status, const char *message) {
  r->started = r->ended = true;
  atomic_store(&r->control->cancelled, true);
  if (cft_stream_respond(r->stream, status, "text/plain", message, strlen(message)) < 0)
    cft_stream_reset(r->stream);
}

static void body(cft_stream_t *stream, void *ctx, const uint8_t *data, size_t len) {
  (void)stream;
  direct_request_t *r = ctx;
  if (r->ended) return;
  if (len > r->request.content_len - r->received) {
    reject(r, 400, "Invalid request body\n");
    return;
  }
  if (len) memcpy((char *)r->request.body + r->received, data, len);
  r->received += len;
}

static void body_end(cft_stream_t *stream, void *ctx) {
  (void)stream;
  direct_request_t *r = ctx;
  if (r->ended) return;
  if (r->received != r->request.content_len) reject(r, 400, "Incomplete request\n");
  else r->body_done = true;
}

static bool decode_block(direct_request_t *r) {
  decoder_t *d = r->decoder;
  if (!d) {
    if (r->response.gzip_size < 18 || memcmp(r->response.gzip, "\x1f\x8b\x08\x00", 4)) return false;
#if CONFIG_FLUE_DIAG_ASSETS_INTERNAL
    d = heap_caps_calloc(1, sizeof *d, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
#else
    d = buffer_memory_calloc(1, sizeof *d);
#endif
    if (!d) return false;
    tinfl_init(&d->inflater);
    r->decoder = d;
  }
  size_t input = r->response.gzip_size - 18 - d->consumed;
  size_t output = TINFL_LZ_DICT_SIZE;
  d->status = tinfl_decompress(&d->inflater, r->response.gzip + 10 + d->consumed,
                              &input, d->dictionary, d->dictionary, &output, 0);
  d->consumed += input; d->produced += output;
  d->sent = 0; d->available = output;
  if (d->produced > r->response.size) return false;
  if (d->status == TINFL_STATUS_DONE)
    return d->produced == r->response.size && d->consumed == r->response.gzip_size - 18;
  return d->status == TINFL_STATUS_HAS_MORE_OUTPUT && output > 0;
}

static void writable(cft_stream_t *stream, void *ctx) {
  direct_request_t *r = ctx;
  if (!r->started || r->ended || cft_stream_buffered(stream)) return;
  const char *data = r->response.body ? r->response.body + r->sent : NULL;
  size_t count = r->response.size - r->sent;
  if (r->response.gzip) {
    if ((!r->decoder || r->decoder->sent == r->decoder->available) && !decode_block(r)) {
      cft_stream_reset(stream);
      return;
    }
    data = (const char *)r->decoder->dictionary + r->decoder->sent;
    count = r->decoder->available - r->decoder->sent;
  }
  if (count > DIRECT_CHUNK) count = DIRECT_CHUNK;
  if (count && cft_stream_write(stream, data, count) < 0) {
    cft_stream_reset(stream);
    return;
  }
  if (r->decoder) r->decoder->sent += count;
  r->sent += count;
  if (r->sent == r->response.size) {
    r->ended = true;
    cft_stream_end(stream);
  }
}

static void start_response(direct_request_t *r) {
  if (r->response.failed) { reject(r, 503, "Insufficient memory\n"); return; }
  cft_header_t headers[WEB_RESPONSE_HEADERS + 1];
  size_t count = 0;
  for (size_t i = 0; i < r->response.header_count; i++)
    headers[count++] = (cft_header_t){r->response.headers[i].name, r->response.headers[i].value};
  char length[24];
  snprintf(length, sizeof length, "%zu", r->response.size);
  bool no_body = r->response.status == 304 || r->response.status == 204;
  if (!no_body) headers[count++] = (cft_header_t){"content-length", length};
  r->started = true;
  if (cft_stream_send_headers(r->stream, r->response.status, headers, count) < 0) {
    cft_stream_reset(r->stream);
    return;
  }
  if (no_body || !r->response.size) {
    r->ended = true;
    cft_stream_end(r->stream);
  } else writable(r->stream, r);
}

static void handle_on_http_task(void *arg) {
  direct_request_t *r = arg;
  if (!atomic_load(&r->control->cancelled)) {
    r->response.status = 200;
    web_set_type(&r->request, "text/html");
    web_dispatch(&r->request);
    if (!r->response.sent) r->response.failed = true;
  }
  atomic_store(&r->control->done, true);  // Publishes the complete response to on_poll.
  atomic_store(&http_busy, false);
  release_request(r);
}

void cloudflare_http_poll(int64_t now_us) {
  direct_request_t *oldest = NULL;
  for (size_t i = 0; i < DIRECT_REQUESTS; i++) {
    direct_request_t *r = pending[i];
    if (!r || r->started) continue;
    if (now_us >= r->deadline) { reject(r, 503, "Request timed out\n"); continue; }
    if (atomic_load(&r->control->done)) { start_response(r); continue; }
    if (r->body_done && !r->dispatched && (!oldest || r->ticket < oldest->ticket)) oldest = r;
  }
  if (!oldest || atomic_exchange(&http_busy, true)) return;
  oldest->dispatched = true;
  atomic_fetch_add(&oldest->control->refs, 1);
  if (rest_api_queue_work(handle_on_http_task, oldest) != ESP_OK) {
    oldest->dispatched = false;
    atomic_store(&http_busy, false);
    release_request(oldest);
  }
}

void cloudflare_http_request(cft_stream_t *stream, const cft_request_t *req, int64_t now_us) {
  static const char *names[] = {"cookie", "origin", "content-type", "if-none-match", "accept-encoding"};
  size_t slot = 0;
  while (slot < DIRECT_REQUESTS && pending[slot]) slot++;
  if (slot == DIRECT_REQUESTS) { cft_stream_respond(stream, 503, NULL, NULL, 0); return; }
  size_t path_len = strlen(req->path), host_len = strlen(req->authority);
  if (path_len >= 512 || host_len >= 160) { cft_stream_respond(stream, 414, NULL, NULL, 0); return; }
  size_t lengths[5] = {0}, copies[5] = {0};
  size_t bytes = path_len + host_len + 2;
  for (size_t i = 0; i < req->num_headers; i++) {
    for (size_t j = 0; j < 5; j++) {
      if (strcasecmp(req->headers[i].name, names[j])) continue;
      if ((j == 1 || j == 2) && copies[j]) { cft_stream_respond(stream, 400, NULL, NULL, 0); return; }
      size_t len = strlen(req->headers[i].value);
      size_t added = len + (copies[j] ? 2 : 0);
      if (added > 4096 || bytes > 4096 - added) {
        cft_stream_respond(stream, 431, NULL, NULL, 0); return;
      }
      lengths[j] += added; bytes += added; copies[j]++;
    }
  }
  size_t content_len = req->content_length > 0 ? req->content_length : 0;
  if (content_len >= 8192) { cft_stream_respond(stream, 413, NULL, NULL, 0); return; }
  direct_request_t *r = buffer_memory_calloc(1, sizeof *r);
  if (!r) { cft_stream_respond(stream, 503, NULL, NULL, 0); return; }
  r->control = heap_caps_calloc(1, sizeof *r->control, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  if (!r->control) { free(r); cft_stream_respond(stream, 503, NULL, NULL, 0); return; }
  atomic_init(&r->control->refs, 1); atomic_init(&r->control->done, false); atomic_init(&r->control->cancelled, false);
  r->storage_size = bytes + 5 + content_len + 1;
  r->storage = buffer_memory_calloc(1, r->storage_size);
  if (!r->storage) { release_request(r); cft_stream_respond(stream, 503, NULL, NULL, 0); return; }
  char *p = r->storage;
  memcpy(p, req->path, path_len + 1); r->request.uri = p; p += path_len + 1;
  memcpy(p, req->authority, host_len + 1); r->headers[0] = (web_header_t){"Host", p}; p += host_len + 1;
  size_t count = 1;
  for (size_t j = 0; j < 5; j++) {
    if (!copies[j]) continue;
    r->headers[count++] = (web_header_t){names[j], p};
    size_t offset = 0;
    for (size_t i = 0; i < req->num_headers; i++) {
      if (strcasecmp(req->headers[i].name, names[j])) continue;
      if (offset) { memcpy(p + offset, j == 0 ? "; " : ", ", 2); offset += 2; }
      size_t len = strlen(req->headers[i].value);
      memcpy(p + offset, req->headers[i].value, len); offset += len;
    }
    p += lengths[j] + 1;
  }
  r->request.headers = r->headers; r->request.header_count = count;
  r->request.method = !strcmp(req->method, "POST") ? HTTP_POST : HTTP_GET;
  r->request.content_len = content_len; r->request.body = p; r->request.response = &r->response;
  r->stream = stream; r->slot = slot; r->deadline = now_us + DIRECT_TIMEOUT_US; r->ticket = ++next_ticket;
  pending[slot] = r;
  const cft_stream_handlers_t handlers = {.on_body = body, .on_body_end = body_end, .on_writable = writable, .on_close = closed};
  cft_stream_set_handlers(stream, &handlers, r);
  if (cft_stream_body_ended(stream)) body_end(stream, r);
}
