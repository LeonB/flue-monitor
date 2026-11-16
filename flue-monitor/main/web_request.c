#include "web_request.h"
#include "buffer_memory.h"
#include "compressed_assets.h"
#include "asset_encoding.h"
#include <stdlib.h>
#include <string.h>
#include <strings.h>

static const web_route_t *routes[52];
static size_t route_count;

static esp_err_t native_handler(httpd_req_t *native) {
  const web_route_t *route = native->user_ctx;
  web_request_t req = {.native = native, .method = native->method,
    .uri = native->uri, .content_len = native->content_len};
  return route->handler(&req);
}

esp_err_t web_register_handler(httpd_handle_t server, const web_route_t *route) {
  if (route_count == sizeof routes / sizeof routes[0]) return ESP_ERR_NO_MEM;
  const httpd_uri_t native = {.uri = route->uri, .method = route->method,
    .handler = native_handler, .user_ctx = (void *)route};
  esp_err_t err = httpd_register_uri_handler(server, &native);
  if (err == ESP_OK) routes[route_count++] = route;
  return err;
}

esp_err_t web_dispatch(web_request_t *req) {
  size_t len = strcspn(req->uri, "?");
  for (size_t i = 0; i < route_count; i++) {
    const web_route_t *route = routes[i];
    if (route->method == req->method && strlen(route->uri) == len && !memcmp(route->uri, req->uri, len))
      return route->handler(req);
  }
  return web_send_err(req, HTTPD_404_NOT_FOUND, "Not found");
}

void web_response_clear(web_response_t *r) {
  for (size_t i = 0; i < r->header_count; i++) free((void *)r->headers[i].name);
  if (r->owned) free((void *)r->body);
  memset(r, 0, sizeof *r);
}

bool web_request_is_tunnel(const web_request_t *req) { return !req->native; }
int web_req_to_sockfd(web_request_t *req) { return req->native ? httpd_req_to_sockfd(req->native) : -1; }

esp_err_t web_header(web_request_t *req, const char *name, char *out, size_t size) {
  if (req->native) return httpd_req_get_hdr_value_str(req->native, name, out, size);
  for (size_t i = 0; i < req->header_count; i++) {
    if (strcasecmp(req->headers[i].name, name)) continue;
    const char *value = req->headers[i].value;
    if (strlen(value) >= size) return ESP_ERR_HTTPD_RESULT_TRUNC;
    memcpy(out, value, strlen(value) + 1);
    return ESP_OK;
  }
  return ESP_ERR_NOT_FOUND;
}

esp_err_t web_query(web_request_t *req, char *out, size_t size) {
  if (req->native) return httpd_req_get_url_query_str(req->native, out, size);
  const char *query = strchr(req->uri, '?');
  if (!query) return ESP_ERR_NOT_FOUND;
  query++;
  if (strlen(query) >= size) return ESP_ERR_HTTPD_RESULT_TRUNC;
  memcpy(out, query, strlen(query) + 1);
  return ESP_OK;
}

int web_recv(web_request_t *req, char *out, size_t size) {
  if (req->native) return httpd_req_recv(req->native, out, size);
  if (size > req->content_len - req->received) size = req->content_len - req->received;
  if (size) memcpy(out, req->body + req->received, size);
  req->received += size;
  return size;
}

esp_err_t web_set_header(web_request_t *req, const char *name, const char *value) {
  if (req->native) return httpd_resp_set_hdr(req->native, name, value);
  web_response_t *r = req->response;
  size_t index = 0;
  while (index < r->header_count && strcasecmp(r->headers[index].name, name)) index++;
  size_t bytes = strlen(name) + strlen(value) + 2;
  if (index == WEB_RESPONSE_HEADERS || bytes > 4096 - r->header_bytes) goto fail;
  char *copy = buffer_memory_alloc(bytes);
  if (!copy) goto fail;
  memcpy(copy, name, strlen(name) + 1);
  char *v = copy + strlen(name) + 1;
  memcpy(v, value, strlen(value) + 1);
  if (index < r->header_count) {
    r->header_bytes -= strlen(r->headers[index].name) + strlen(r->headers[index].value) + 2;
    free((void *)r->headers[index].name);
  } else r->header_count++;
  r->headers[index] = (web_header_t){copy, v};
  r->header_bytes += bytes;
  return ESP_OK;
fail:
  r->failed = true;
  return ESP_ERR_NO_MEM;
}

esp_err_t web_set_type(web_request_t *req, const char *type) {
  return req->native ? httpd_resp_set_type(req->native, type) : web_set_header(req, "Content-Type", type);
}
esp_err_t web_set_status(web_request_t *req, const char *status) {
  if (req->native) return httpd_resp_set_status(req->native, status);
  req->response->status = atoi(status);
  return ESP_OK;
}

esp_err_t web_send_ref(web_request_t *req, const char *data, size_t size) {
  if (req->native) return httpd_resp_send(req->native, data, size);
  web_response_t *r = req->response;
  if (r->sent) return ESP_ERR_INVALID_STATE;
  r->body = data; r->size = size; r->sent = true;
  return ESP_OK;
}
esp_err_t web_send(web_request_t *req, const char *data, ssize_t size) {
  if (size < 0) size = data ? strlen(data) : 0;
  if (req->native) return httpd_resp_send(req->native, data, size);
  char *copy = size ? buffer_memory_alloc(size) : NULL;
  if (size && !copy) { req->response->failed = true; return ESP_ERR_NO_MEM; }
  if (size) memcpy(copy, data, size);
  esp_err_t err = web_send_ref(req, copy, size);
  if (err != ESP_OK) free(copy);
  else req->response->owned = true;
  return err;
}
esp_err_t web_sendstr(web_request_t *req, const char *data) { return web_send(req, data, strlen(data)); }
esp_err_t web_send_owned(web_request_t *req, char *data) {
  if (!data) return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory");
  esp_err_t err = web_send_ref(req, data, strlen(data));
  if (req->native || err != ESP_OK) free(data);
  else req->response->owned = true;
  return err;
}

esp_err_t web_send_err(web_request_t *req, httpd_err_code_t error, const char *message) {
  if (req->native) return httpd_resp_send_err(req->native, error, message);
  const char *status = "500 Internal Server Error";
  switch (error) {
    case HTTPD_400_BAD_REQUEST: status = "400 Bad Request"; break;
    case HTTPD_401_UNAUTHORIZED: status = "401 Unauthorized"; break;
    case HTTPD_403_FORBIDDEN: status = "403 Forbidden"; break;
    case HTTPD_404_NOT_FOUND: status = "404 Not Found"; break;
    case HTTPD_408_REQ_TIMEOUT: status = "408 Request Timeout"; break;
    default: break;
  }
  web_set_status(req, status);
  web_set_type(req, "text/html");
  return web_sendstr(req, message ? message : status);
}

bool web_accepts_gzip(web_request_t *req) {
  if (req->native) return compressed_asset_accepts_gzip(req->native);
  char encodings[160];
  if (web_header(req, "Accept-Encoding", encodings, sizeof encodings) != ESP_OK) return false;
  return asset_encoding_accepts_gzip(encodings);
}

esp_err_t web_send_identity(web_request_t *req, const unsigned char *gzip, size_t size, size_t raw_size) {
  if (req->native) return compressed_asset_send_identity(req->native, gzip, size, raw_size);
  esp_err_t err = web_send_ref(req, NULL, raw_size);
  req->response->gzip = gzip;
  req->response->gzip_size = size;
  return err;
}
