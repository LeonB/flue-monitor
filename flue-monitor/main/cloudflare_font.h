#pragma once
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "cf_tunnel.h"
#include "buffer_memory.h"

typedef struct {
  const char *path, *data, *end, *etag;
} cloudflare_font_t;

typedef struct {
  const char *data;
  size_t size, sent;
} cloudflare_font_response_t;

static void font_closed(cft_stream_t *stream, void *ctx, bool completed) {
  (void)stream; (void)completed;
  free(ctx);
}

static void font_writable(cft_stream_t *stream, void *ctx) {
  cloudflare_font_response_t *response = ctx;
  if (cft_stream_buffered(stream) || response->sent == response->size) return;
  size_t count = response->size - response->sent;
  if (count > 512) count = 512;
  if (cft_stream_write(stream, response->data + response->sent, count) < 0) {
    cft_stream_reset(stream);
    return;
  }
  response->sent += count;
  if (response->sent == response->size) cft_stream_end(stream);
}

// Public fonts only. Authentication, API requests and other assets use HTTPD.
static bool cloudflare_serve_font(cft_stream_t *stream, const char *uri,
                                  const cloudflare_font_t *fonts, size_t count) {
  size_t path_len = strcspn(uri, "?");
  const cloudflare_font_t *font = NULL;
  for (size_t i = 0; i < count; i++) {
    if (strlen(fonts[i].path) == path_len && !memcmp(fonts[i].path, uri, path_len)) {
      font = &fonts[i];
      break;
    }
  }
  if (!font) return false;
  bool versioned = false;
  const char *query = uri[path_len] ? uri + path_len + 1 : NULL;
  // Noncanonical queries retain HTTPD's existing validation/error semantics.
  if (query) {
    if (strlen(query) != 26 || strncasecmp(query, "v=", 2) ||
        memcmp(query + 2, font->etag + 1, 24)) return false;
    versioned = true;
  }
  const char *condition = cft_stream_header(stream, "if-none-match");
  bool unchanged = condition && strlen(condition) < 256 &&
                   (strstr(condition, font->etag) || !strcmp(condition, "*"));
  size_t size = font->end - font->data;
  char length[24];
  snprintf(length, sizeof length, "%zu", size);
  cft_header_t headers[] = {
    {"content-type", "font/woff2"}, {"etag", font->etag},
    {"cache-control", versioned ? "private, max-age=31536000, immutable" : "no-cache"},
    {"content-length", length},
  };
  cloudflare_font_response_t *response = NULL;
  if (!unchanged) {
    response = buffer_memory_alloc(sizeof *response);
    if (!response) {
      cft_stream_respond(stream, 503, NULL, NULL, 0);
      return true;
    }
    *response = (cloudflare_font_response_t){font->data, size, 0};
    const cft_stream_handlers_t handlers = {.on_writable = font_writable, .on_close = font_closed};
    cft_stream_set_handlers(stream, &handlers, response);
  }
  if (cft_stream_send_headers(stream, unchanged ? 304 : 200, headers, unchanged ? 3 : 4) < 0) {
    cft_stream_reset(stream);
    return true;
  }
  if (unchanged || !size) cft_stream_end(stream);
  else font_writable(stream, response);
  return true;
}
