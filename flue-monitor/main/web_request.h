#pragma once

#include "esp_http_server.h"
#include <stdbool.h>

#define WEB_RESPONSE_HEADERS 12
typedef struct { const char *name, *value; } web_header_t;
typedef struct {
  int status;
  web_header_t headers[WEB_RESPONSE_HEADERS];
  size_t header_count, header_bytes;
  const char *body;
  size_t size;
  bool owned, failed, sent;
  const unsigned char *gzip;
  size_t gzip_size;
} web_response_t;

// Handlers run on the shared HTTP task for both transports. A direct request
// owns its captured headers/body; it never pretends to be an SDK request.
typedef struct {
  httpd_method_t method;
  const char *uri;
  size_t content_len;
  httpd_req_t *native;
  const web_header_t *headers;
  size_t header_count;
  const char *body;
  size_t received;
  web_response_t *response;
} web_request_t;
typedef struct {
  const char *uri;
  httpd_method_t method;
  esp_err_t (*handler)(web_request_t *req);
} web_route_t;

esp_err_t web_register_handler(httpd_handle_t server, const web_route_t *route);
esp_err_t web_dispatch(web_request_t *req);
void web_response_clear(web_response_t *response);
bool web_request_is_tunnel(const web_request_t *req);
int web_req_to_sockfd(web_request_t *req);
esp_err_t web_header(web_request_t *req, const char *name, char *out, size_t size);
esp_err_t web_query(web_request_t *req, char *out, size_t size);
int web_recv(web_request_t *req, char *out, size_t size);
esp_err_t web_set_header(web_request_t *req, const char *name, const char *value);
esp_err_t web_set_type(web_request_t *req, const char *type);
esp_err_t web_set_status(web_request_t *req, const char *status);
esp_err_t web_send(web_request_t *req, const char *data, ssize_t size);
esp_err_t web_sendstr(web_request_t *req, const char *data);
// Transfer a heap string to the response (also frees it after a native send).
esp_err_t web_send_owned(web_request_t *req, char *data);
// Borrow immutable, long-lived data, such as an asset stored in flash.
esp_err_t web_send_ref(web_request_t *req, const char *data, size_t size);
esp_err_t web_send_err(web_request_t *req, httpd_err_code_t error, const char *message);
bool web_accepts_gzip(web_request_t *req);
esp_err_t web_send_identity(web_request_t *req, const unsigned char *gzip, size_t size, size_t raw_size);
