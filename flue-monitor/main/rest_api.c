#include "rest_api.h"
#include "web_request.h"

#include <math.h>
#include <float.h>
#include <ctype.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "history_snapshot.h"

#include "cJSON.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "lwip/sockets.h"

#include "sensors.h"
#include "settings.h"
#include "dashboard_auth.h"
#include "cloudflare_tunnel.h"
#include "memory_diagnostics.h"
#include "sheets_logger.h"
#include "refill_notify.h"
#include "ws_server.h"
#include "web_assets_generated.h"
#include "compressed_assets.h"
#include "buffer_memory.h"
#include "stack_diagnostics.h"

static const char *TAG = "rest_api";

static bool auth_required(web_request_t *req) {
  if (dashboard_auth_check(req)) return false;
  web_set_header(req, "Cache-Control", "no-store");
  web_set_header(req, "WWW-Authenticate", "Session");
  web_send_err(req, HTTPD_401_UNAUTHORIZED, "Sign in required");
  return true;
}

// Initial password enrollment is allowed only through a LAN hostname/IP.
// Never let a remote tunnel visitor race to claim a factory-fresh device.
static bool auth_setup_is_remote(web_request_t *req) {
  return dashboard_auth_is_remote(req);
}



static esp_err_t auth_status_handler(web_request_t *req) {
  char body[80];
  bool configured = dashboard_auth_is_configured();
  snprintf(body, sizeof body, "{\"configured\":%s,\"setup_local_only\":%s}",
           configured ? "true" : "false", !configured && auth_setup_is_remote(req) ? "true" : "false");
  web_set_type(req, "application/json");
  web_set_header(req, "Cache-Control", "no-store");
  return web_sendstr(req, body);
}
static const web_route_t auth_status_uri = { .uri="/api/auth/status", .method=HTTP_GET, .handler=auth_status_handler };

static esp_err_t auth_form_handler(web_request_t *req) {
  if ((strcmp(req->uri, "/api/auth/password") == 0 || strcmp(req->uri, "/api/auth/logout") == 0) && auth_required(req)) return ESP_FAIL;
  if (!dashboard_auth_check_csrf(req)) return web_send_err(req, HTTPD_403_FORBIDDEN, "Invalid request origin");
  if (req->content_len <= 0 || req->content_len > 512) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid request");
  char *body = buffer_memory_calloc(req->content_len + 1, 1);
  if (!body) return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory");
  if (!web_read_body(req, body, req->content_len)) {
    memset(body, 0, req->content_len + 1);
    free(body);
    return web_send_err(req, HTTPD_400_BAD_REQUEST, "Incomplete request");
  }
  cJSON *root = cJSON_Parse(body);
  memset(body, 0, req->content_len + 1);
  free(body);
  if (!root) return web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
  const cJSON *pw = cJSON_GetObjectItemCaseSensitive(root, "password");
  const cJSON *remember = cJSON_GetObjectItemCaseSensitive(root, "remember");
  bool keep_signed_in = cJSON_IsTrue(remember);
  const cJSON *current = cJSON_GetObjectItemCaseSensitive(root, "current_password");
  const cJSON *confirm = cJSON_GetObjectItemCaseSensitive(root, "confirm_password");
  esp_err_t err = ESP_ERR_INVALID_ARG;
  bool setup = strcmp(req->uri, "/api/auth/setup") == 0;
  if (setup && auth_setup_is_remote(req)) {
    cJSON_Delete(root);
    return web_send_err(req, HTTPD_403_FORBIDDEN, "Set the first password from your home network");
  }
  if (pw && (!cJSON_IsString(pw) || strlen(pw->valuestring) < 8 || strlen(pw->valuestring) > 128)) {
    cJSON_Delete(root);
    web_set_type(req, "application/json");
    web_set_status(req, "400 Bad Request");
    return web_sendstr(req, "{\"error\":\"Password must be 8–128 characters.\"}");
  }
  char password_copy[129] = {0};
  if (cJSON_IsString(pw) && strlen(pw->valuestring) < sizeof password_copy)
    strlcpy(password_copy, pw->valuestring, sizeof password_copy);
  if (setup && !dashboard_auth_is_configured() && cJSON_IsString(pw) && cJSON_IsString(confirm) &&
      strcmp(pw->valuestring, confirm->valuestring) == 0)
    err = dashboard_auth_set_password(NULL, password_copy);
  else if (!setup && strcmp(req->uri, "/api/auth/login") == 0 && cJSON_IsString(pw))
    err = dashboard_auth_login(req, password_copy, keep_signed_in);
  else if (strcmp(req->uri, "/api/auth/password") == 0 && dashboard_auth_check_csrf(req) && cJSON_IsString(current) && cJSON_IsString(pw) &&
           cJSON_IsString(confirm) && strcmp(pw->valuestring, confirm->valuestring) == 0)
    err = dashboard_auth_set_password(current->valuestring, pw->valuestring);
  else if (strcmp(req->uri, "/api/auth/logout") == 0 && dashboard_auth_check_csrf(req)) {
    err = dashboard_auth_logout(req);
    if (err != ESP_OK) {
      cJSON_Delete(root);
      return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Could not save sign-out. Please try again.");
    }
    cJSON_Delete(root);
    web_set_type(req, "application/json");
    return web_sendstr(req, "{\"success\":true}");
  }
  cJSON_Delete(root);
  if (err == ESP_OK) {
    web_set_type(req, "application/json");
    web_set_header(req, "Cache-Control", "no-store");
    if (strcmp(req->uri, "/api/auth/login") == 0)
      return web_sendstr(req, "{\"success\":true}");
    if (strcmp(req->uri, "/api/auth/setup") == 0) {
      // First-use setup signs in the owner immediately after persisting.
      err = dashboard_auth_login(req, password_copy, keep_signed_in);
      if (err != ESP_OK)
        return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Password saved. Please sign in again.");
      return web_sendstr(req, "{\"success\":true}");
    }
    return web_sendstr(req, "{\"success\":true,\"reauthenticate\":true}");
  }
  if (err == ESP_ERR_INVALID_STATE) {
    web_set_type(req, "application/json");
    web_set_status(req, "503 Service Unavailable");
    return web_sendstr(req, "{\"error\":\"Waiting for the monitor clock. Please try again shortly.\"}");
  }
  if (err != ESP_ERR_NOT_FOUND && err != ESP_ERR_TIMEOUT && err != ESP_ERR_INVALID_ARG)
    return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Could not save sign-in. Please try again.");
  web_set_type(req, "application/json");
  const char *status = err == ESP_ERR_NOT_FOUND ? "401 Unauthorized" :
                       err == ESP_ERR_TIMEOUT ? "429 Too Many Requests" : "400 Bad Request";
  web_set_status(req, status);
  return web_sendstr(req, err == ESP_ERR_NOT_FOUND ? "{\"error\":\"Password is incorrect.\"}" :
                             err == ESP_ERR_TIMEOUT ? "{\"error\":\"Too many attempts. Wait 30 seconds and try again.\"}" :
                             "{\"error\":\"Password must be 8–128 characters and both entries must match.\"}");
}
static const web_route_t auth_login_uri = { .uri="/api/auth/login", .method=HTTP_POST, .handler=auth_form_handler };
static const web_route_t auth_setup_uri = { .uri="/api/auth/setup", .method=HTTP_POST, .handler=auth_form_handler };
static const web_route_t auth_password_uri = { .uri="/api/auth/password", .method=HTTP_POST, .handler=auth_form_handler };
static const web_route_t auth_logout_uri = { .uri="/api/auth/logout", .method=HTTP_POST, .handler=auth_form_handler };

// Text assets are stored only as gzip; WOFF2 files are already compressed.
extern const char web_ui_font_caprasimo_400_start[] asm("_binary_caprasimo_400_woff2_start");
extern const char web_ui_font_caprasimo_400_end[] asm("_binary_caprasimo_400_woff2_end");
extern const char web_ui_font_figtree_400_start[] asm("_binary_figtree_variable_woff2_start");
extern const char web_ui_font_figtree_400_end[] asm("_binary_figtree_variable_woff2_end");

// Versioned static assets stay fresh for a year; legacy URLs and HTML revalidate.
// Gzip clients use flash directly; identity clients stream through the ROM inflater.

static esp_err_t serve_asset(web_request_t *req, const char *type,
                             const char *raw, size_t raw_len, const char *raw_etag,
                             const unsigned char *gzip, size_t gzip_len, const char *gzip_etag) {
  // Fonts and app identity assets are public for sign-in and home screen discovery.
  if (strcmp(type, "font/woff2") != 0 && strncmp(type, "image/", 6) != 0
      && strcmp(type, "application/manifest+json") != 0
      && strcmp(req->uri, "/service-worker.js") != 0 && strcmp(req->uri, "/loading.html") != 0
      && auth_required(req)) return ESP_FAIL;
  bool versioned = false;
  const bool can_version = strcmp(type, "text/html") != 0 &&
                           strncmp(req->uri, "/service-worker.js", 18) != 0;
  if (can_version && strchr(req->uri, '?')) {
    char query[160], version[32];
    if (web_query(req, query, sizeof query) != ESP_OK) {
      web_set_header(req, "Cache-Control", "no-store");
      return web_send_err(req, HTTPD_400_BAD_REQUEST, "Asset query too long");
    }
    esp_err_t result = httpd_query_key_value(query, "v", version, sizeof version);
    if (result == ESP_ERR_NOT_FOUND && web_request_is_tunnel(req) &&
        !strcmp(type, "font/woff2") && strlen(query) == 26 &&
        !strncasecmp(query, "v=", 2) && !memcmp(query + 2, raw_etag + 1, 24)) {
      memcpy(version, query + 2, 25);
      result = ESP_OK;
    }
    if (result != ESP_ERR_NOT_FOUND) {
      // Hash the identity bytes, independent of Accept-Encoding and its ETag.
      if (result != ESP_OK || strlen(version) != 24 ||
          strncmp(version, raw_etag + 1, 24) != 0) {
        web_set_header(req, "Cache-Control", "no-store");
        return web_send_err(req, HTTPD_404_NOT_FOUND, "Asset version unavailable; reload the page");
      }
      versioned = true;
    }
  }
  bool compressed = gzip && web_accepts_gzip(req);
  const char *etag = compressed ? gzip_etag : raw_etag;
  char condition[256];
  bool unchanged = web_header(req, "If-None-Match", condition, sizeof(condition)) == ESP_OK
                   && (strstr(condition, etag) || strcmp(condition, "*") == 0);
  web_set_type(req, type);
  web_set_header(req, "Cache-Control", versioned ? "private, max-age=31536000, immutable" : "no-cache");
  web_set_header(req, "ETag", etag);
  if (gzip) web_set_header(req, "Vary", "Accept-Encoding");
  if (compressed) web_set_header(req, "Content-Encoding", "gzip");
  if (unchanged) {
    web_set_status(req, "304 Not Modified");
    return web_send(req, NULL, 0);
  }
  if (!compressed && !raw) return web_send_identity(req, gzip, gzip_len, raw_len);
  return web_send_ref(req, compressed ? (const char *)gzip : raw, compressed ? gzip_len : raw_len);
}

// iOS fetches the matching launch image during home screen installation.
static esp_err_t web_service_worker_get_handler(web_request_t *req) {
  return serve_asset(req, "application/javascript", NULL, ASSET_service_worker_RAW_SIZE,
    ASSET_service_worker_ETAG, asset_service_worker_gzip, sizeof(asset_service_worker_gzip), ASSET_service_worker_GZIP_ETAG);
}
static const web_route_t web_service_worker_uri = { .uri="/service-worker.js", .method=HTTP_GET, .handler=web_service_worker_get_handler };

static esp_err_t web_loading_get_handler(web_request_t *req) {
  return serve_asset(req, "text/html", NULL, ASSET_loading_RAW_SIZE,
    ASSET_loading_ETAG, asset_loading_gzip, sizeof(asset_loading_gzip), ASSET_loading_GZIP_ETAG);
}
static const web_route_t web_loading_uri = { .uri="/loading.html", .method=HTTP_GET, .handler=web_loading_get_handler };

static esp_err_t web_startup_get_handler(web_request_t *req) {
  char query[64], size[24];
  if (web_query(req, query, sizeof(query)) != ESP_OK ||
      httpd_query_key_value(query, "size", size, sizeof(size)) != ESP_OK)
    return web_send_err(req, HTTPD_404_NOT_FOUND, "Unknown launch image");
  static const struct {
    const char *size, *etag, *gzip_etag;
    const unsigned char *gzip;
    size_t raw_size, gzip_size;
  } images[] = {
#define STARTUP_IMAGE(dim) {#dim, ASSET_startup_##dim##_ETAG, ASSET_startup_##dim##_GZIP_ETAG, \
    asset_startup_##dim##_gzip, ASSET_startup_##dim##_RAW_SIZE, sizeof(asset_startup_##dim##_gzip)}
    STARTUP_IMAGE(640x1136),
    STARTUP_IMAGE(750x1334),
    STARTUP_IMAGE(1242x2208),
    STARTUP_IMAGE(1125x2436),
    STARTUP_IMAGE(828x1792),
    STARTUP_IMAGE(1242x2688),
    STARTUP_IMAGE(1170x2532),
    STARTUP_IMAGE(1179x2556),
    STARTUP_IMAGE(1206x2622),
    STARTUP_IMAGE(1284x2778),
    STARTUP_IMAGE(1290x2796),
    STARTUP_IMAGE(1320x2868),
    STARTUP_IMAGE(1260x2736),
    STARTUP_IMAGE(1080x2340),
#undef STARTUP_IMAGE
  };
  for (size_t i = 0; i < sizeof images / sizeof images[0]; i++) {
    if (!strcmp(size, images[i].size))
      return serve_asset(req, "image/png", NULL, images[i].raw_size, images[i].etag,
                         images[i].gzip, images[i].gzip_size, images[i].gzip_etag);
  }
  return web_send_err(req, HTTPD_404_NOT_FOUND, "Unknown launch image");
}
static const web_route_t web_startup_uri = { .uri="/startup.png", .method=HTTP_GET, .handler=web_startup_get_handler };

static esp_err_t web_stove_svg_get_handler(web_request_t *req) {
  return serve_asset(req, "image/svg+xml", NULL, ASSET_stove_svg_RAW_SIZE,
                     ASSET_stove_svg_ETAG, asset_stove_svg_gzip, sizeof(asset_stove_svg_gzip), ASSET_stove_svg_GZIP_ETAG);
}
static const web_route_t web_stove_svg_uri = { .uri="/flue-icon-stove.svg", .method=HTTP_GET, .handler=web_stove_svg_get_handler };

static esp_err_t web_favicon_get_handler(web_request_t *req) {
  return serve_asset(req, "image/x-icon", NULL, ASSET_favicon_RAW_SIZE,
                     ASSET_favicon_ETAG, asset_favicon_gzip, sizeof(asset_favicon_gzip), ASSET_favicon_GZIP_ETAG);
}
static const web_route_t web_favicon_uri = { .uri="/favicon.ico", .method=HTTP_GET, .handler=web_favicon_get_handler };

static esp_err_t web_apple_icon_get_handler(web_request_t *req) {
  return serve_asset(req, "image/png", NULL, ASSET_apple_icon_RAW_SIZE,
                     ASSET_apple_icon_ETAG, asset_apple_icon_gzip, sizeof(asset_apple_icon_gzip), ASSET_apple_icon_GZIP_ETAG);
}
static const web_route_t web_apple_icon_uri = { .uri="/apple-touch-icon.png", .method=HTTP_GET, .handler=web_apple_icon_get_handler };

static esp_err_t web_icon_192_get_handler(web_request_t *req) {
  return serve_asset(req, "image/png", NULL, ASSET_icon_192_RAW_SIZE,
                     ASSET_icon_192_ETAG, asset_icon_192_gzip, sizeof(asset_icon_192_gzip), ASSET_icon_192_GZIP_ETAG);
}
static const web_route_t web_icon_192_uri = { .uri="/icon-192.png", .method=HTTP_GET, .handler=web_icon_192_get_handler };

static esp_err_t web_icon_512_get_handler(web_request_t *req) {
  return serve_asset(req, "image/png", NULL, ASSET_icon_512_RAW_SIZE,
                     ASSET_icon_512_ETAG, asset_icon_512_gzip, sizeof(asset_icon_512_gzip), ASSET_icon_512_GZIP_ETAG);
}
static const web_route_t web_icon_512_uri = { .uri="/icon-512.png", .method=HTTP_GET, .handler=web_icon_512_get_handler };

static esp_err_t web_manifest_get_handler(web_request_t *req) {
  return serve_asset(req, "application/manifest+json", NULL, ASSET_manifest_RAW_SIZE,
                     ASSET_manifest_ETAG, asset_manifest_gzip, sizeof(asset_manifest_gzip), ASSET_manifest_GZIP_ETAG);
}
static const web_route_t web_manifest_uri = { .uri="/site.webmanifest", .method=HTTP_GET, .handler=web_manifest_get_handler };

static esp_err_t web_ui_burn_graph_js_get_handler(web_request_t *req) {
  return serve_asset(req, "application/javascript", NULL, ASSET_burn_graph_js_RAW_SIZE,
                     ASSET_burn_graph_js_ETAG, asset_burn_graph_js_gzip, sizeof(asset_burn_graph_js_gzip), ASSET_burn_graph_js_GZIP_ETAG);
}
static const web_route_t web_ui_burn_graph_js_uri = {.uri = "/burn-graph.js", .method = HTTP_GET, .handler = web_ui_burn_graph_js_get_handler};

static esp_err_t web_ui_uplot_js_get_handler(web_request_t *req) {
  return serve_asset(req, "application/javascript", NULL, ASSET_uplot_js_RAW_SIZE,
                     ASSET_uplot_js_ETAG, asset_uplot_js_gzip, sizeof(asset_uplot_js_gzip), ASSET_uplot_js_GZIP_ETAG);
}
static const web_route_t web_ui_uplot_js_uri = {.uri = "/vendor/uplot.min.js", .method = HTTP_GET, .handler = web_ui_uplot_js_get_handler};

static esp_err_t web_ui_uplot_css_get_handler(web_request_t *req) {
  return serve_asset(req, "text/css", NULL, ASSET_uplot_css_RAW_SIZE,
                     ASSET_uplot_css_ETAG, asset_uplot_css_gzip, sizeof(asset_uplot_css_gzip), ASSET_uplot_css_GZIP_ETAG);
}
static const web_route_t web_ui_uplot_css_uri = {.uri = "/vendor/uplot.min.css", .method = HTTP_GET, .handler = web_ui_uplot_css_get_handler};

static esp_err_t web_ui_html_get_handler(web_request_t *req) {
  if (!dashboard_auth_check(req)) {
    web_set_type(req, "text/html; charset=utf-8");
    web_set_header(req, "Cache-Control", "no-store");
    if (strcmp(req->uri, "/login")) {
      web_set_status(req, "303 See Other");
      web_set_header(req, "Location", "/login");
      return web_sendstr(req, "Sign in at /login");
    }
    web_set_header(req, "Vary", "Accept-Encoding");
    if (web_accepts_gzip(req)) {
      web_set_header(req, "Content-Encoding", "gzip");
      return web_send_ref(req, (const char *)asset_login_gzip, sizeof asset_login_gzip);
    }
    return web_send_identity(req, asset_login_gzip, sizeof asset_login_gzip, ASSET_login_RAW_SIZE);
  }
  return serve_asset(req, "text/html", NULL, ASSET_html_RAW_SIZE,
                     ASSET_html_ETAG, asset_html_gzip, sizeof(asset_html_gzip), ASSET_html_GZIP_ETAG);
}
static const web_route_t web_ui_html_uri = {.uri = "/", .method = HTTP_GET, .handler = web_ui_html_get_handler};
// Real document navigation: password managers must see the login at /login.
static const web_route_t web_ui_login_uri = {.uri = "/login", .method = HTTP_GET, .handler = web_ui_html_get_handler};

static esp_err_t web_ui_js_get_handler(web_request_t *req) {
  return serve_asset(req, "application/javascript", NULL, ASSET_js_RAW_SIZE,
                     ASSET_js_ETAG, asset_js_gzip, sizeof(asset_js_gzip), ASSET_js_GZIP_ETAG);
}
static const web_route_t web_ui_js_uri = {.uri = "/dashboard.js", .method = HTTP_GET, .handler = web_ui_js_get_handler};

static esp_err_t web_ui_css_get_handler(web_request_t *req) {
  const compressed_asset_t *asset = portal_styles_asset();
  return serve_asset(req, "text/css", NULL, asset->raw_size, asset->etag,
                     asset->data, asset->size, asset->gzip_etag);
}
static const web_route_t web_ui_css_uri = {.uri = "/dashboard.css", .method = HTTP_GET, .handler = web_ui_css_get_handler};

static esp_err_t web_ui_alpine_js_get_handler(web_request_t *req) {
  const compressed_asset_t *asset = portal_alpine_asset();
  return serve_asset(req, "application/javascript", NULL, asset->raw_size, asset->etag,
                     asset->data, asset->size, asset->gzip_etag);
}
static const web_route_t web_ui_alpine_js_uri = {
    .uri = "/alpinejs.min.js", .method = HTTP_GET, .handler = web_ui_alpine_js_get_handler};

// Self-hosted Caprasimo/Figtree woff2 files -- see dashboard.html's own
// comment for why these are embedded rather than loaded from Google's CDN.
static esp_err_t web_ui_font_caprasimo_400_get_handler(web_request_t *req) {
  return serve_asset(req, "font/woff2", web_ui_font_caprasimo_400_start,
                     web_ui_font_caprasimo_400_end - web_ui_font_caprasimo_400_start, ASSET_caprasimo_400_ETAG, NULL, 0, NULL);
}
static const web_route_t web_ui_font_caprasimo_400_uri = {
    .uri = "/fonts/caprasimo-400.woff2", .method = HTTP_GET, .handler = web_ui_font_caprasimo_400_get_handler};

static esp_err_t web_ui_font_figtree_400_get_handler(web_request_t *req) {
  return serve_asset(req, "font/woff2", web_ui_font_figtree_400_start,
                     web_ui_font_figtree_400_end - web_ui_font_figtree_400_start, ASSET_figtree_400_ETAG, NULL, 0, NULL);
}
static const web_route_t web_ui_font_figtree_variable_uri = {
    .uri = "/fonts/figtree-variable.woff2", .method = HTTP_GET, .handler = web_ui_font_figtree_400_get_handler};
static const web_route_t web_ui_font_figtree_400_uri = {
    .uri = "/fonts/figtree-400.woff2", .method = HTTP_GET, .handler = web_ui_font_figtree_400_get_handler};

static const web_route_t web_ui_font_figtree_600_uri = {
    .uri = "/fonts/figtree-600.woff2", .method = HTTP_GET, .handler = web_ui_font_figtree_400_get_handler};

static const web_route_t web_ui_font_figtree_700_uri = {
    .uri = "/fonts/figtree-700.woff2", .method = HTTP_GET, .handler = web_ui_font_figtree_400_get_handler};

// cJSON_AddNumberToObject widens our floats to double and prints the
// shortest round-tripping decimal for *that* double -- which surfaces the
// float's own binary-representation noise (e.g. 24.188323974609375 instead
// of 24.2). Rounding to a sensible decimal precision first, matching what
// the ESPHome sidecar's own str_sprintf precision already used for these
// same values, gets a clean API response instead.
static double round_to(double value, double step) {
  return round(value / step) * step;
}

char *rest_api_reading_json(const sensor_reading_t *r) {
  cJSON *root = cJSON_CreateObject();
  cJSON_AddBoolToObject(root, "thermocouple_ok", r->thermocouple_ok);
  cJSON_AddNumberToObject(root, "thermocouple_c", round_to(r->thermocouple_c, 0.1));
  cJSON_AddNumberToObject(root, "cold_junction_c", round_to(r->cold_junction_c, 0.1));
  cJSON_AddNumberToObject(root, "thermocouple_rate_c_per_min", round_to(r->thermocouple_rate_c_per_min, 0.01));
  cJSON_AddStringToObject(root, "thermocouple_zone", thermocouple_zone_name(r->thermocouple_zone));
  memory_diagnostics_add_json(root);

  char *json = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  return json;
}

static esp_err_t reading_get_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  sensor_reading_t r;
  sensors_get_last_reading(&r);

  char *json = rest_api_reading_json(&r);
  web_set_type(req, "application/json");
  web_send_owned(req, json);
  return ESP_OK;
}

static const web_route_t reading_uri = {
    .uri = "/api/reading",
    .method = HTTP_GET,
    .handler = reading_get_handler,
};

// Live WiFi link quality -- esp_wifi_sta_get_ap_info() queries the current
// association fresh on every call (unlike RSSI, which the WiFi driver only
// ever logs once, at the moment it associates -- see CLAUDE.md's own
// writeup of chasing an apparent REST API hang that turned out to be a
// weak signal after roaming to a farther AP within the same SSID). No
// caching here: this is meant to answer "how's the signal right now," not
// "how was it at boot."
static esp_err_t wifi_get_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  wifi_ap_record_t info;
  esp_err_t err = esp_wifi_sta_get_ap_info(&info);

  cJSON *root = cJSON_CreateObject();
  cJSON_AddBoolToObject(root, "connected", err == ESP_OK);
  if (err == ESP_OK) {
    cJSON_AddStringToObject(root, "ssid", (const char *) info.ssid);
    char bssid[18];
    snprintf(bssid, sizeof(bssid), "%02x:%02x:%02x:%02x:%02x:%02x", info.bssid[0], info.bssid[1], info.bssid[2],
             info.bssid[3], info.bssid[4], info.bssid[5]);
    cJSON_AddStringToObject(root, "bssid", bssid);
    cJSON_AddNumberToObject(root, "channel", info.primary);
    cJSON_AddNumberToObject(root, "rssi", info.rssi);
  }

  char *json = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  web_set_type(req, "application/json");
  web_send_owned(req, json);
  return ESP_OK;
}

static const web_route_t wifi_get_uri = {
    .uri = "/api/wifi",
    .method = HTTP_GET,
    .handler = wifi_get_handler,
};

static esp_err_t devices_wifi_get_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  wifi_ap_record_t info;
  bool monitor_connected = esp_wifi_sta_get_ap_info(&info) == ESP_OK;
  int display_rssi = 0;
  bool display_connected = ws_server_display_wifi(&display_rssi);
  cJSON *root = cJSON_CreateObject();
  cJSON *monitor = cJSON_AddObjectToObject(root, "monitor");
  cJSON *display = cJSON_AddObjectToObject(root, "display");
  cJSON_AddBoolToObject(monitor, "connected", monitor_connected);
  if (monitor_connected) cJSON_AddNumberToObject(monitor, "rssi", info.rssi);
  else cJSON_AddNullToObject(monitor, "rssi");
  cJSON_AddBoolToObject(display, "connected", display_connected);
  if (display_connected) cJSON_AddNumberToObject(display, "rssi", display_rssi);
  else cJSON_AddNullToObject(display, "rssi");
  char *json = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  web_set_type(req, "application/json");
  web_set_header(req, "Cache-Control", "no-store");
  esp_err_t result = web_send_owned(req, json);
  return result;
}
static const web_route_t devices_wifi_get_uri = {
    .uri = "/api/devices/wifi", .method = HTTP_GET, .handler = devices_wifi_get_handler,
};

static void settings_to_json(const settings_t *s, cJSON *root) {
  cJSON_AddBoolToObject(root, "refill_enabled", s->refill.enabled);
  cJSON_AddNumberToObject(root, "refill_threshold_c", s->refill.threshold_c);
  cJSON_AddBoolToObject(root, "refill_quiet_enabled", s->refill.quiet_enabled);
  cJSON_AddNumberToObject(root, "refill_quiet_start_min", s->refill.quiet_start_min);
  cJSON_AddNumberToObject(root, "refill_quiet_end_min", s->refill.quiet_end_min);
  // A public ntfy topic URL acts as a subscription secret. Do not expose it
  // through the credential-free settings endpoint used by flue-display.
  cJSON_AddBoolToObject(root, "refill_url_set", *s->refill.url != 0);
  cJSON_AddBoolToObject(root, "refill_token_set", *s->refill.token != 0);
  cJSON_AddBoolToObject(root, "cloudflare_enabled", s->cloudflare.enabled);
  cJSON_AddStringToObject(root, "cloudflare_hostname", s->cloudflare.hostname);
  cJSON_AddNumberToObject(root, "cloudflare_connections", s->cloudflare.connections);
  cJSON_AddBoolToObject(root, "cloudflare_token_set", *s->cloudflare.token != 0);
  cJSON_AddNumberToObject(root, "settings_revision", ws_server_settings_revision(false));
  cJSON_AddNumberToObject(root, "log_heartbeat_min", s->log_heartbeat_min);
  cJSON_AddNumberToObject(root, "burn_end_temperature_c", round_to(s->burn_end_temperature_c, 0.1));
  cJSON_AddNumberToObject(root, "zone_cold_max_c", round_to(s->zone_cold_max_c, 0.1));
  cJSON_AddNumberToObject(root, "zone_optimal_max_c", round_to(s->zone_optimal_max_c, 0.1));
  cJSON_AddNumberToObject(root, "fast_rise_c_per_min", round_to(s->fast_rise_c_per_min, 0.1));
  cJSON_AddNumberToObject(root, "thermocouple_deadband_c", round_to(s->thermocouple_deadband_c, 0.1));
  cJSON_AddStringToObject(root, "google_sheets_webhook_url", s->google_sheets_webhook_url);
  cJSON_AddStringToObject(root, "google_sheets_secret", s->google_sheets_secret);
  cJSON_AddNumberToObject(root, "idle_pulse_period_ms", s->idle_pulse_period_ms);
  cJSON_AddNumberToObject(root, "fast_pulse_period_ms", s->fast_pulse_period_ms);
  cJSON_AddNumberToObject(root, "rate_deadband_c_per_min", round_to(s->rate_deadband_c_per_min, 0.1));
  cJSON_AddNumberToObject(root, "color_transition_exponent", round_to(s->color_transition_exponent, 0.1));
  cJSON_AddStringToObject(root, "zone_cold_color", s->zone_cold_color);
  cJSON_AddStringToObject(root, "zone_optimal_color", s->zone_optimal_color);
  cJSON_AddStringToObject(root, "zone_hot_color", s->zone_hot_color);
  cJSON_AddNumberToObject(root, "maximum_brightness", s->maximum_brightness);
  cJSON_AddNumberToObject(root, "minimum_brightness", s->minimum_brightness);
  cJSON_AddNumberToObject(root, "breathing_exponent", round_to(s->breathing_exponent, 0.1));
}

// Check the JSON double before narrowing it to float or an unsigned integer.
// Domain rules (threshold ordering, positive periods, etc.) stay in settings.c.
static bool json_number(const cJSON *item, double minimum, double maximum, bool integer) {
  return cJSON_IsNumber(item) && isfinite(item->valuedouble) &&
         item->valuedouble >= minimum && item->valuedouble <= maximum &&
         (!integer || floor(item->valuedouble) == item->valuedouble);
}

static esp_err_t settings_get_handler(web_request_t *req) {
  bool device_settings = !web_request_is_tunnel(req) && !dashboard_auth_is_remote(req) && !dashboard_auth_check(req);
  if (!device_settings && auth_required(req)) return ESP_FAIL;
  settings_t *s = buffer_memory_calloc(1, sizeof *s);
  if (!s) return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory");
  settings_get(s);

  cJSON *root = cJSON_CreateObject();
  if (!root) { free(s); return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory"); }
  settings_to_json(s, root);
  free(s);
  if (web_request_is_tunnel(req) || device_settings || dashboard_auth_is_remote(req)) {
    cJSON_DeleteItemFromObject(root, "google_sheets_secret");
    cJSON_DeleteItemFromObject(root, "google_sheets_webhook_url");
    cJSON_AddBoolToObject(root, "credentials_redacted", true);
  }

  char *json = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  if (!json) return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory");
  web_set_type(req, "application/json");
  web_send_owned(req, json);
  return ESP_OK;
}

static const web_route_t settings_get_uri = {
    .uri = "/api/settings",
    .method = HTTP_GET,
    .handler = settings_get_handler,
};

// Original scalar tuning fields default to zero when omitted. Later fields
// (palette, brightness, shape, burn end, Cloudflare and refill) retain saved
// values for older clients. Omitted Sheets credentials also retain saved values;
// explicit empty Sheets strings clear them, while blank CF/refill secrets retain.
static esp_err_t settings_post_handler(web_request_t *req) {
  // Local commissioning is allowed before the owner sets the first password.
  // Tunnel visitors always require a session, even before setup.
  if ((dashboard_auth_is_configured() || dashboard_auth_is_remote(req)) && auth_required(req)) return ESP_FAIL;
  if (!dashboard_auth_check_csrf(req)) return web_send_err(req, HTTPD_403_FORBIDDEN, "Invalid request origin");
  if (req->content_len <= 0 || req->content_len >= 8192) {
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Request body too large");
    return ESP_FAIL;
  }

  char *body = buffer_memory_calloc(req->content_len + 1, 1);
  if (!body) {
    web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory");
    return ESP_FAIL;
  }
  if (!web_read_body(req, body, req->content_len)) {
    free(body);
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Incomplete request");
    return ESP_FAIL;
  }

  cJSON *root = cJSON_Parse(body);
  free(body);
  if (root == NULL) {
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
    return ESP_FAIL;
  }

  // Per-request snapshots: PSRAM only on the monitor, released on every exit.
  settings_t *snapshots = buffer_memory_calloc(2, sizeof *snapshots);
  if (!snapshots) {
    cJSON_Delete(root);
    return web_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Insufficient memory");
  }
  settings_t *s = &snapshots[0], *current = &snapshots[1];
  settings_get(current);
  const char *float_keys[] = {"zone_cold_max_c", "zone_optimal_max_c", "fast_rise_c_per_min",
    "thermocouple_deadband_c", "rate_deadband_c_per_min", "color_transition_exponent",
    "breathing_exponent", "burn_end_temperature_c", "refill_threshold_c"};
  for (size_t i = 0; i < sizeof float_keys / sizeof float_keys[0]; i++) {
    const cJSON *value = cJSON_GetObjectItem(root, float_keys[i]);
    if (value && !json_number(value, -FLT_MAX, FLT_MAX, false)) goto invalid_number;
  }
  const char *integer_keys[] = {"log_heartbeat_min", "idle_pulse_period_ms", "fast_pulse_period_ms"};
  for (size_t i = 0; i < sizeof integer_keys / sizeof integer_keys[0]; i++) {
    const cJSON *value = cJSON_GetObjectItem(root, integer_keys[i]);
    if (value && !json_number(value, 0, UINT16_MAX, true)) goto invalid_number;
  }
  memcpy(s->google_sheets_webhook_url, current->google_sheets_webhook_url, sizeof s->google_sheets_webhook_url);
  memcpy(s->google_sheets_secret, current->google_sheets_secret, sizeof s->google_sheets_secret);
  cJSON *item;
  s->refill = current->refill;
  const char *refill_bools[] = {"refill_enabled", "refill_quiet_enabled"};
  uint32_t *refill_flags[] = {&s->refill.enabled, &s->refill.quiet_enabled};
  for (int i = 0; i < 2; ++i) {
    item = cJSON_GetObjectItemCaseSensitive(root, refill_bools[i]);
    if (item && !cJSON_IsBool(item)) goto invalid_refill;
    if (item) *refill_flags[i] = cJSON_IsTrue(item);
  }
  item = cJSON_GetObjectItemCaseSensitive(root, "refill_threshold_c");
  if (item) s->refill.threshold_c = item->valuedouble;
  const char *quiet_keys[] = {"refill_quiet_start_min", "refill_quiet_end_min"};
  uint32_t *quiet_values[] = {&s->refill.quiet_start_min, &s->refill.quiet_end_min};
  for (int i = 0; i < 2; ++i) {
    item = cJSON_GetObjectItemCaseSensitive(root, quiet_keys[i]);
    if (item && !json_number(item, 0, 1439, true)) goto invalid_refill;
    if (item) *quiet_values[i] = item->valuedouble;
  }
  const char *refill_strings[] = {"refill_url", "refill_token"};
  char *refill_values[] = {s->refill.url, s->refill.token};
  const size_t refill_sizes[] = {sizeof s->refill.url, sizeof s->refill.token};
  for (int i = 0; i < 2; ++i) {
    item = cJSON_GetObjectItemCaseSensitive(root, refill_strings[i]);
    if (item && (!cJSON_IsString(item) || strlen(item->valuestring) >= refill_sizes[i])) goto invalid_refill;
    if (item && *item->valuestring) strcpy(refill_values[i], item->valuestring);
  }

  item = cJSON_GetObjectItem(root, "log_heartbeat_min");
  s->log_heartbeat_min = cJSON_IsNumber(item) ? (uint16_t) item->valuedouble : 0;

  item = cJSON_GetObjectItem(root, "zone_cold_max_c");
  s->zone_cold_max_c = cJSON_IsNumber(item) ? (float) item->valuedouble : 0.0f;

  // Older clients retain the saved session threshold when omitting this field.
  item = cJSON_GetObjectItem(root, "burn_end_temperature_c");
  s->burn_end_temperature_c = item ? (float)item->valuedouble : current->burn_end_temperature_c;

  item = cJSON_GetObjectItem(root, "zone_optimal_max_c");
  s->zone_optimal_max_c = cJSON_IsNumber(item) ? (float) item->valuedouble : 0.0f;

  item = cJSON_GetObjectItem(root, "fast_rise_c_per_min");
  s->fast_rise_c_per_min = cJSON_IsNumber(item) ? (float) item->valuedouble : 0.0f;

  item = cJSON_GetObjectItem(root, "thermocouple_deadband_c");
  s->thermocouple_deadband_c = cJSON_IsNumber(item) ? (float) item->valuedouble : 0.0f;

  item = cJSON_GetObjectItem(root, "google_sheets_webhook_url");
  if (cJSON_IsString(item)) {
    strlcpy(s->google_sheets_webhook_url, item->valuestring, sizeof(s->google_sheets_webhook_url));
  }

  item = cJSON_GetObjectItem(root, "google_sheets_secret");
  if (cJSON_IsString(item)) {
    strlcpy(s->google_sheets_secret, item->valuestring, sizeof(s->google_sheets_secret));
  }

  item = cJSON_GetObjectItem(root, "idle_pulse_period_ms");
  s->idle_pulse_period_ms = cJSON_IsNumber(item) ? (uint16_t) item->valuedouble : 0;

  item = cJSON_GetObjectItem(root, "fast_pulse_period_ms");
  s->fast_pulse_period_ms = cJSON_IsNumber(item) ? (uint16_t) item->valuedouble : 0;

  item = cJSON_GetObjectItem(root, "rate_deadband_c_per_min");
  s->rate_deadband_c_per_min = cJSON_IsNumber(item) ? (float) item->valuedouble : 0.0f;

  item = cJSON_GetObjectItem(root, "color_transition_exponent");
  s->color_transition_exponent = cJSON_IsNumber(item) ? (float) item->valuedouble : 0.0f;

  // Older API clients omit colours: retain those already saved. Explicit
  // values must be exactly #RRGGBB; never truncate invalid input into validity.
  s->cloudflare = current->cloudflare;
  item = cJSON_GetObjectItemCaseSensitive(root, "cloudflare_enabled");
  if (item && !cJSON_IsBool(item)) goto invalid_cloudflare;
  if (item) s->cloudflare.enabled = cJSON_IsTrue(item);
  item = cJSON_GetObjectItemCaseSensitive(root, "cloudflare_connections");
  if (item && !json_number(item, 1, 4, true)) goto invalid_cloudflare;
  if (item) s->cloudflare.connections = (uint32_t)item->valuedouble;
  const char *cf_keys[] = {"cloudflare_hostname", "cloudflare_token"};
  char *cf_values[] = {s->cloudflare.hostname, s->cloudflare.token};
  size_t cf_sizes[] = {sizeof s->cloudflare.hostname, sizeof s->cloudflare.token};
  for (int i = 0; i < 2; i++) {
    item = cJSON_GetObjectItemCaseSensitive(root, cf_keys[i]);
    if (!item) continue;
    if (!cJSON_IsString(item) || strlen(item->valuestring) >= cf_sizes[i]) goto invalid_cloudflare;
    if (i == 1 && !*item->valuestring) continue; // blank preserves stored token
    strcpy(cf_values[i], item->valuestring);
    if (i == 0) for (char *c = cf_values[i]; *c; c++) *c = tolower((unsigned char)*c);
  }
  item = cJSON_GetObjectItemCaseSensitive(root, "minimum_brightness");
  if (item != NULL && !json_number(item, 0, 255, true)) {
    cJSON_Delete(root);
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Minimum brightness must be an integer from 0 to 255");
    free(snapshots);
    return ESP_FAIL;
  }
  s->minimum_brightness = item == NULL ? current->minimum_brightness : (uint32_t) item->valuedouble;
  item = cJSON_GetObjectItemCaseSensitive(root, "maximum_brightness");
  if (item != NULL && !json_number(item, 0, 255, true)) {
    cJSON_Delete(root);
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Maximum brightness must be an integer from 0 to 255");
    free(snapshots);
    return ESP_FAIL;
  }
  s->maximum_brightness = item == NULL ? current->maximum_brightness : (uint32_t) item->valuedouble;
  item = cJSON_GetObjectItemCaseSensitive(root, "breathing_exponent");
  s->breathing_exponent = item == NULL ? current->breathing_exponent : (float) item->valuedouble;
  const char *keys[] = {"zone_cold_color", "zone_optimal_color", "zone_hot_color"};
  char *colors[] = {s->zone_cold_color, s->zone_optimal_color, s->zone_hot_color};
  const char *previous[] = {current->zone_cold_color, current->zone_optimal_color, current->zone_hot_color};
  for (int i = 0; i < 3; i++) {
    item = cJSON_GetObjectItemCaseSensitive(root, keys[i]);
    if (item == NULL) {
      memcpy(colors[i], previous[i], 8);
    } else if (cJSON_IsString(item) && strlen(item->valuestring) == 7) {
      memcpy(colors[i], item->valuestring, 8);
    } else {
      cJSON_Delete(root);
      web_send_err(req, HTTPD_400_BAD_REQUEST, "Colours must be #RRGGBB");
      free(snapshots);
      return ESP_FAIL;
    }
  }
  cJSON_Delete(root);

  esp_err_t err = settings_set(s);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "Rejected settings update: %s", esp_err_to_name(err));
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid settings values");
    free(snapshots);
    return ESP_FAIL;
  }

  // Lets flue-display (and any other WS client) know its cached zone
  // thresholds are stale, without waiting for its own next poll cycle.
  uint32_t revision = ws_server_settings_revision(true);
  ws_server_broadcast_settings_changed();

  web_set_type(req, "application/json");
  char response[192];
  snprintf(response, sizeof(response), "{\"success\":true,\"settings_revision\":%lu,\"cloudflare_token_set\":%s,\"refill_url_set\":%s,\"refill_token_set\":%s}",
           (unsigned long) revision, *s->cloudflare.token ? "true" : "false",
           *s->refill.url ? "true" : "false", *s->refill.token ? "true" : "false");
  web_sendstr(req, response);
  if (memcmp(&current->cloudflare, &s->cloudflare, sizeof s->cloudflare)) cloudflare_tunnel_start();
  free(snapshots);
  return ESP_OK;

invalid_number:
  cJSON_Delete(root);
  free(snapshots);
  return web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid numeric setting");

invalid_refill:
  cJSON_Delete(root);
  free(snapshots);
  return web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid refill notification setting");

invalid_cloudflare:
  cJSON_Delete(root);
  web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid Cloudflare setting type or length");
  free(snapshots);
  return ESP_FAIL;
}

static const web_route_t settings_post_uri = {
    .uri = "/api/settings",
    .method = HTTP_POST,
    .handler = settings_post_handler,
};


// The append-only woodstove-event taxonomy, starting with the original
// ESPHome sidecar's own template buttons (same slugs, so any future
// analysis joining against old Sheets data doesn't need a mapping table).
// A closed set rather than free-text event labels, deliberately: this is
// the data-gathering phase's whole point (see the repo root CLAUDE.md) --
// a consistent, known taxonomy is what makes burns comparable to each
// other later, which free-text annotations from a rushed tap at the stove
// would not reliably give.
typedef struct {
  const char *slug;
  const char *label;
} woodstove_event_t;

static const woodstove_event_t EVENTS[] = {
    {"cold_start", "Cold Start"},
    {"opened_stove", "Opened Stove"},
    {"added_wood", "Added Wood"},
    {"damper_up", "Damper Up"},
    {"damper_down", "Damper Down"},
    {"burning_optimally", "Burning Optimally"},
    {"roaring", "Stove Roaring"},
    {"dying_down", "Dying Down"},
    {"fire_out", "Fire Out"},
    {"stove_off", "Stove Off"},
    {"coaling", "Coaling"}, // Append only: array indexes are saved event IDs.
};
#define EVENT_COUNT (sizeof(EVENTS) / sizeof(EVENTS[0]))

// Returns EVENTS[]'s own canonical slug pointer on a match (so callers can
// hang onto it, e.g. in the event log ring buffer below, without copying),
// or NULL if `slug` isn't one of the fixed taxonomy.
static const char *event_slug_canonical(const char *slug) {
  for (size_t i = 0; i < EVENT_COUNT; i++) {
    if (strcmp(EVENTS[i].slug, slug) == 0) {
      return EVENTS[i].slug;
    }
  }
  return NULL;
}

// A small separate ring buffer of *logged* events (as opposed to EVENTS[]
// above, the fixed menu of what's loggable) -- GET /api/history includes
// these as markers on the 24h graph, matching the design mockup's dots on
// the curve. 64 comfortably covers a burn's worth of taps; older ones just
// age out, same as the sensor history ring buffer.
#define EVENT_LOG_CAPACITY 64
typedef struct {
  uint32_t uptime_s;
  const char *slug;  // points into EVENTS[]'s own static strings, never freed
} logged_event_t;
static logged_event_t s_event_log[EVENT_LOG_CAPACITY];
static size_t s_event_log_count = 0;
static size_t s_event_log_head = 0;

static void event_log_push(const char *slug) {
  s_event_log[s_event_log_head] = (logged_event_t){
      .uptime_s = (uint32_t) (esp_timer_get_time() / 1000000),
      .slug = slug,
  };
  s_event_log_head = (s_event_log_head + 1) % EVENT_LOG_CAPACITY;
  if (s_event_log_count < EVENT_LOG_CAPACITY) {
    s_event_log_count++;
  }
}

// The Mac owns the backup and elapsed time; import/export run on the shared
// HTTP task. Sensor sampling uses its existing mutex.

static esp_err_t history_apply(history_snapshot_t *saved) {
  uint32_t now = esp_timer_get_time() / 1000000;
  if (!history_snapshot_valid(saved, EVENT_COUNT) ||
      !history_snapshot_rebase(saved, now)) return ESP_ERR_INVALID_ARG;
  esp_err_t err = sensors_merge_history(saved->samples, saved->sample_count, now);
  if (err != ESP_OK) return err;
  logged_event_t fresh[EVENT_LOG_CAPACITY];
  size_t n = s_event_log_count;
  size_t start = (s_event_log_head + EVENT_LOG_CAPACITY - n) % EVENT_LOG_CAPACITY;
  for (size_t i = 0; i < n; i++) fresh[i] = s_event_log[(start + i) % EVENT_LOG_CAPACITY];
  s_event_log_head = s_event_log_count = 0;
  size_t a = 0, b = 0;
  while (a < saved->event_count || b < n) {
    bool same = a < saved->event_count && b < n && saved->events[a].age_s == now - fresh[b].uptime_s &&
                EVENTS[saved->events[a].event_id].slug == fresh[b].slug;
    bool old = !same && a < saved->event_count && (b == n || saved->events[a].age_s >= now - fresh[b].uptime_s);
    logged_event_t event = old ? (logged_event_t){now - saved->events[a].age_s, EVENTS[saved->events[a].event_id].slug} : fresh[b];
    if (old || same) a++;
    if (!old) b++;
    s_event_log[s_event_log_head] = event;
    s_event_log_head = (s_event_log_head + 1) % EVENT_LOG_CAPACITY;
    if (s_event_log_count < EVENT_LOG_CAPACITY) s_event_log_count++;
  }
  return ESP_OK;
}

esp_err_t rest_api_history_export(void *buffer, size_t *size) {
  if (!buffer) { *size = sizeof(history_snapshot_t); return ESP_OK; }
  if (*size != sizeof(history_snapshot_t)) return ESP_ERR_INVALID_SIZE;
  history_snapshot_t *saved = buffer;
  memset(saved, 0, sizeof *saved);
  saved->version = HISTORY_SNAPSHOT_VERSION;
  // saved_at is stamped by the Mac after receipt; device wall-clock is irrelevant.
  uint32_t now = esp_timer_get_time() / 1000000;
  saved->sample_count = sensors_get_history(saved->samples, SENSORS_HISTORY_CAPACITY);
  for (size_t i = 0; i < saved->sample_count; i++) saved->samples[i].uptime_s = now - saved->samples[i].uptime_s;
  saved->event_count = s_event_log_count;
  size_t start = (s_event_log_head + EVENT_LOG_CAPACITY - s_event_log_count) % EVENT_LOG_CAPACITY;
  for (size_t i = 0; i < s_event_log_count; i++) {
    logged_event_t *e = &s_event_log[(start + i) % EVENT_LOG_CAPACITY];
    saved->events[i].age_s = now - e->uptime_s;
    for (size_t id = 0; id < EVENT_COUNT; id++) if (e->slug == EVENTS[id].slug) saved->events[i].event_id = id;
  }
  return history_snapshot_valid(saved, EVENT_COUNT) ? ESP_OK : ESP_ERR_INVALID_ARG;
}

// RAM-only restore of a Mac-owned snapshot, rebased by the supplied elapsed time.
esp_err_t rest_api_history_import(const char *body, size_t size) {
  if (size != sizeof(history_snapshot_t)) return ESP_ERR_INVALID_SIZE;
  history_snapshot_t *saved = buffer_memory_alloc(size);
  if (!saved) return ESP_ERR_NO_MEM;
  memcpy(saved, body, size);
  esp_err_t err = ESP_ERR_INVALID_ARG;
  if (history_snapshot_valid(saved, EVENT_COUNT)) err = history_apply(saved);
  free(saved);
  return err;
}

static esp_err_t events_get_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  cJSON *root = cJSON_CreateArray();
  for (size_t i = 0; i < EVENT_COUNT; i++) {
    cJSON *item = cJSON_CreateObject();
    cJSON_AddStringToObject(item, "slug", EVENTS[i].slug);
    cJSON_AddStringToObject(item, "label", EVENTS[i].label);
    cJSON_AddItemToArray(root, item);
  }

  char *json = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  web_set_type(req, "application/json");
  web_send_owned(req, json);
  return ESP_OK;
}

static const web_route_t events_get_uri = {
    .uri = "/api/events",
    .method = HTTP_GET,
    .handler = events_get_handler,
};

// Queues an immediate, un-gated Sheets log tagged with the given event slug
// -- see sheets_logger_log_event()'s own doc comment for why this bypasses
// the periodic deadband/heartbeat check and doesn't reset its clock.
static esp_err_t event_post_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  if (!dashboard_auth_check_csrf(req)) return web_send_err(req, HTTPD_403_FORBIDDEN, "Invalid request origin");
  if (req->content_len <= 0 || req->content_len >= 128) {
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Request body too large");
    return ESP_FAIL;
  }

  char body[128] = {0};
  if (!web_read_body(req, body, req->content_len)) {
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Incomplete request");
    return ESP_FAIL;
  }

  cJSON *root = cJSON_Parse(body);
  if (root == NULL) {
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
    return ESP_FAIL;
  }

  cJSON *item = cJSON_GetObjectItem(root, "event");
  const char *canonical = cJSON_IsString(item) ? event_slug_canonical(item->valuestring) : NULL;
  cJSON_Delete(root);
  if (canonical == NULL) {
    web_send_err(req, HTTPD_400_BAD_REQUEST, "Unknown event -- see GET /api/events for valid slugs");
    return ESP_FAIL;
  }

  // Recorded locally either way -- event_log_push() feeds GET /api/events
  // and the dashboard's own event sheet/graph markers, independent of
  // whether the Sheets-delivery queue (below) had room. Deliberately NOT
  // gated on sheets_logger_log_event()'s result: an earlier version of this
  // handler responded with an HTTP error (implying "try again") whenever the
  // Sheets queue was full, but the local record above had *already*
  // succeeded by then -- a user retrying in response to that error message
  // would call event_log_push() a second time for the same tap, duplicating
  // the local annotation even though only the Sheets delivery, not the tap
  // itself, needed retrying. Reporting a normal 200 with a `sheets_queued`
  // flag instead (see below) means there's nothing to retry -- the queue
  // draining on its own is what actually resolves this, not another tap.
  event_log_push(canonical);
  refill_notify_manual_event(canonical);
  bool sheets_queued = sheets_logger_log_event(canonical);
  if (!sheets_queued) {
    ESP_LOGW(TAG, "Sheets log queue full -- '%s' recorded locally but not queued for Sheets", canonical);
  }

  char resp_body[64];
  snprintf(resp_body, sizeof(resp_body), "{\"success\":true,\"sheets_queued\":%s}", sheets_queued ? "true" : "false");
  web_set_type(req, "application/json");
  web_sendstr(req, resp_body);
  return ESP_OK;
}

static const web_route_t event_post_uri = {
    .uri = "/api/event",
    .method = HTTP_POST,
    .handler = event_post_handler,
};

// Backs the web UI's graph. Samples use a four-minute cadence with stable
// runs compressed (see sensors.h's history_sample_t); events are the last
// EVENT_LOG_CAPACITY logged annotations, both returned oldest-first as
// compact [age_s, ...] arrays rather than repeated-key objects, to keep
// this cheap to build even at (a still-small) 360+64 entries. age_s is
// seconds before "now" (this response's own timestamp), not a raw uptime
// value the client would otherwise need this device's boot time to
// interpret.
static esp_err_t history_get_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  uint32_t now_s = (uint32_t) (esp_timer_get_time() / 1000000);

#if CONFIG_FLUE_DIAG_HISTORY_API_INTERNAL
  history_sample_t *samples = heap_caps_malloc(SENSORS_HISTORY_CAPACITY * sizeof(*samples), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
#else
  history_sample_t *samples = buffer_memory_alloc(SENSORS_HISTORY_CAPACITY * sizeof(*samples));
#endif
  if (!samples) {
    web_set_status(req, "503 Service Unavailable");
    return web_sendstr(req, "History buffer unavailable");
  }
  size_t sample_count = sensors_get_history(samples, SENSORS_HISTORY_CAPACITY);

  cJSON *root = cJSON_CreateObject();
  cJSON_AddNumberToObject(root, "now_s", now_s);

  cJSON *samples_json = cJSON_CreateArray();
  for (size_t i = 0; i < sample_count; i++) {
    cJSON *point = cJSON_CreateArray();
    cJSON_AddItemToArray(point, cJSON_CreateNumber(now_s - samples[i].uptime_s));
    cJSON_AddItemToArray(point, cJSON_CreateNumber(round_to(samples[i].thermocouple_c, 0.1)));
    cJSON_AddItemToArray(point, cJSON_CreateNumber(round_to(samples[i].thermocouple_rate_c_per_min, 0.01)));
    cJSON_AddItemToArray(point, cJSON_CreateNumber(samples[i].thermocouple_zone));
    cJSON_AddItemToArray(samples_json, point);
  }
  cJSON_AddItemToObject(root, "samples", samples_json);
  free(samples);

  cJSON *events_json = cJSON_CreateArray();
  size_t event_start = s_event_log_count < EVENT_LOG_CAPACITY ? 0 : s_event_log_head;
  for (size_t i = 0; i < s_event_log_count; i++) {
    logged_event_t *e = &s_event_log[(event_start + i) % EVENT_LOG_CAPACITY];
    cJSON *point = cJSON_CreateArray();
    cJSON_AddItemToArray(point, cJSON_CreateNumber(now_s - e->uptime_s));
    cJSON_AddItemToArray(point, cJSON_CreateString(e->slug));
    cJSON_AddItemToArray(events_json, point);
  }
  cJSON_AddItemToObject(root, "events", events_json);

  char *json = cJSON_PrintUnformatted(root);
  cJSON_Delete(root);
  web_set_type(req, "application/json");
  web_send_owned(req, json);
  return ESP_OK;
}

static const web_route_t history_get_uri = {
    .uri = "/api/history",
    .method = HTTP_GET,
    .handler = history_get_handler,
};

static esp_err_t settings_status_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  uint32_t revision = ws_server_settings_revision(false);
  char json[112];
  snprintf(json, sizeof(json), "{\"settings_revision\":%lu,\"display_applied\":%s}",
           (unsigned long) revision, ws_server_settings_applied(revision) ? "true" : "false");
  web_set_type(req, "application/json");
  return web_sendstr(req, json);
}
static const web_route_t settings_status_uri = {
    .uri = "/api/settings/status", .method = HTTP_GET, .handler = settings_status_handler,
};

static esp_err_t cloudflare_status_handler(web_request_t *req) {
  if (auth_required(req)) return ESP_FAIL;
  cloudflare_status_t status;
  cloudflare_tunnel_get_status(&status);
  const char *state = "unavailable";
  switch (status.state) {
    case CLOUDFLARE_STATUS_DISABLED: state = "disabled"; break;
    case CLOUDFLARE_STATUS_CONNECTING: state = "connecting"; break;
    case CLOUDFLARE_STATUS_CONNECTED: state = "connected"; break;
    case CLOUDFLARE_STATUS_AUTH_ERROR: state = "auth_error"; break;
    case CLOUDFLARE_STATUS_NETWORK_ERROR: state = "network_error"; break;
  }
  char json[160];
  snprintf(json, sizeof(json), "{\"state\":\"%s\",\"connections\":%lu,\"configured_connections\":%lu}",
           state, (unsigned long)status.connections, (unsigned long)status.configured_connections);
  web_set_type(req, "application/json");
  web_set_header(req, "Cache-Control", "no-store");
  return web_sendstr(req, json);
}
static const web_route_t cloudflare_status_uri = {
    .uri = "/api/cloudflare/status", .method = HTTP_GET, .handler = cloudflare_status_handler,
};

// Explicit, not just relying on HTTPD_DEFAULT_CONFIG()'s own default (also
// 7) -- rest_api_log_socket_usage() below needs to size its client_fds
// buffer to match whatever this is actually set to.
#define REST_API_MAX_OPEN_SOCKETS 7

static httpd_handle_t s_server = NULL;

esp_err_t rest_api_queue_work(httpd_work_fn_t work, void *arg) {
  return s_server ? httpd_queue_work(s_server, work, arg) : ESP_ERR_INVALID_STATE;
}

static void register_http_stack(void *arg) {
  (void)arg;
  stack_diagnostics_register(STACK_HTTP, HTTP_STACK_BYTES);
}

httpd_handle_t rest_api_start(void) {
  dashboard_auth_init();
  httpd_handle_t server = NULL;
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  // Browser cookies and Cloudflare forwarding headers can exceed the 1 KB default.
  // HTTPD grows its request buffer on demand, up to this bound.
  config.max_req_hdr_len = 4096;
  config.stack_size = HTTP_STACK_BYTES;  // shared with OTA; keep existing 8192 bytes
  // default (8) is too few once ota + ws + web_ui + this project's own
  // endpoints are all registered -- 17 handlers as of the 4 embedded-font
  // routes added alongside this comment; sized with headroom rather than
  // exactly 17 so the next endpoint added doesn't silently repeat this same
  // ESP_ERR_HTTPD_HANDLERS_FULL crash-loop (see CLAUDE.md's "max_uri_handlers
  // must cover every endpoint on this server" section for how this was
  // caught: ws_server_register(), always the last one registered, is the
  // one that fails once the ceiling is hit).
  config.max_uri_handlers = 49;
  config.max_open_sockets = REST_API_MAX_OPEN_SOCKETS;
  config.lru_purge_enable = true;
  config.keep_alive_enable = true;
  config.keep_alive_idle = 30;
  config.keep_alive_interval = 10;
  config.keep_alive_count = 3;
  config.open_fn = ws_server_session_open;
  config.close_fn = ws_server_session_close;

  ESP_LOGI(TAG, "Starting REST API server on port %d", config.server_port);
  ESP_ERROR_CHECK(httpd_start(&server, &config));
  if (httpd_queue_work(server, register_http_stack, NULL) != ESP_OK)
    ESP_LOGW(TAG, "HTTP stack measurement registration failed");
  ESP_ERROR_CHECK(web_register_handler(server, &auth_status_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &auth_login_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &auth_setup_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &auth_password_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &auth_logout_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &reading_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &wifi_get_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &devices_wifi_get_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &settings_get_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &settings_status_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &cloudflare_status_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &settings_post_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &events_get_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &event_post_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &history_get_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_burn_graph_js_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_uplot_js_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_uplot_css_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_html_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_login_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_js_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_css_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_alpine_js_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_font_caprasimo_400_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_font_figtree_variable_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_font_figtree_400_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_font_figtree_600_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_ui_font_figtree_700_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_stove_svg_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_favicon_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_apple_icon_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_icon_192_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_icon_512_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_manifest_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_startup_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_service_worker_uri));
  ESP_ERROR_CHECK(web_register_handler(server, &web_loading_uri));
  s_server = server;
  return server;
}

// Diagnostic for chasing an apparent httpd hang (see CLAUDE.md's "The REST
// API server is single-threaded..." section) -- logs the current open
// socket count against REST_API_MAX_OPEN_SOCKETS, plus each fd, so a
// leak/exhaustion pattern (count climbing to the max and staying pinned
// there) is visible in the serial log over time, distinguishing it from a
// single genuinely-wedged request (which would show a low, stable count).
// Called periodically from main.c's sensor_log_task -- no dedicated timer,
// piggybacking its existing ~30s cadence.
void rest_api_log_socket_usage(void) {
  if (s_server == NULL) {
    return;
  }
  int client_fds[REST_API_MAX_OPEN_SOCKETS];
  size_t count = REST_API_MAX_OPEN_SOCKETS;
  esp_err_t err = httpd_get_client_list(s_server, &count, client_fds);
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "httpd_get_client_list failed: %s", esp_err_to_name(err));
    return;
  }

  char fds_str[REST_API_MAX_OPEN_SOCKETS * 5 + 1] = {0};
  size_t pos = 0;
  for (size_t i = 0; i < count && pos < sizeof(fds_str) - 5; i++) {
    struct sockaddr_storage peer;
    socklen_t peer_len = sizeof(peer);
    if (getpeername(client_fds[i], (struct sockaddr *) &peer, &peer_len) == 0) {
      char address[INET6_ADDRSTRLEN];
      const void *ip;
      uint16_t port;
      if (peer.ss_family == AF_INET6) {
        struct sockaddr_in6 *v6 = (struct sockaddr_in6 *) &peer;
        ip = &v6->sin6_addr; port = v6->sin6_port;
      } else {
        struct sockaddr_in *v4 = (struct sockaddr_in *) &peer;
        ip = &v4->sin_addr; port = v4->sin_port;
      }
      inet_ntop(peer.ss_family, ip, address, sizeof(address));
      ESP_LOGI(TAG, "Socket fd=%d peer=%s:%u type=%s", client_fds[i], address, ntohs(port),
               httpd_ws_get_fd_info(s_server, client_fds[i]) == HTTPD_WS_CLIENT_WEBSOCKET ? "WS" : "HTTP");
    }
    pos += snprintf(fds_str + pos, sizeof(fds_str) - pos, "%d ", client_fds[i]);
  }
  ESP_LOGI(TAG, "Open sockets: %u/%d [%s]", (unsigned) count, REST_API_MAX_OPEN_SOCKETS, fds_str);
}
