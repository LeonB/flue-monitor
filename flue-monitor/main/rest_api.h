#pragma once

#include "esp_http_server.h"
#include "cf_tunnel.h"

#include "sensors.h"

#ifdef __cplusplus
extern "C" {
#endif

// Starts the single shared HTTP server for this device's "normal running"
// state (once connected to real WiFi -- the captive portal's own separate
// server covers initial setup) and registers this project's REST
// endpoints on it:
//   GET  /api/reading  -- latest sensor reading + derived rate/zone
//   GET  /api/wifi     -- live WiFi link info (SSID/BSSID/channel/RSSI),
//                         queried fresh on every call, not cached
//   GET  /api/settings -- current runtime settings
//   POST /api/settings -- replace settings wholesale (JSON body)
//   GET  /api/events   -- the fixed woodstove-event taxonomy (slug + label)
//   POST /api/event    -- log an immediate, un-gated Sheets row for one of
//                         those events (JSON body {"event": "<slug>"})
//   GET  /api/history  -- ~24h of downsampled readings + recent logged
//                         events, for the web UI's graph
//   GET  /                -- the embedded web UI (dashboard/graph/settings)
//   GET  /dashboard.js,
//        /dashboard.css,
//        /alpinejs.min.js  -- the web UI's own JS/CSS/Alpine.js assets
//   GET  /fonts/caprasimo-400.woff2,
//        /fonts/figtree-{400,600,700}.woff2
//                         -- self-hosted design-system fonts (embedded, not
//                            loaded from Google's CDN -- see dashboard.html)
// Returns the server handle so other modules (ota_server, ws_server) can
// register their own endpoints onto the same server instead of each
// starting their own (only one httpd can bind port 80 at a time).
httpd_handle_t rest_api_start(void);

// Tunnel-task-only fast path for already-public font resources.
bool rest_api_tunnel_font(cft_stream_t *stream, const char *uri);

// Serializes a reading into the exact same JSON shape GET /api/reading
// returns -- shared with ws_server's own reading broadcast (via main.c) so
// both surfaces agree on one schema. Caller must free() the returned string.
char *rest_api_reading_json(const sensor_reading_t *r);

// Logs the REST API server's current open-socket count (see the .c file's
// own doc comment) -- diagnostic for chasing an apparent server hang.
// Call periodically; a no-op before rest_api_start() has run.
void rest_api_log_socket_usage(void);

// Shared HTTP task only. RAM-only import/export for the Mac's flash backup.
// Transfer format: versioned binary history_snapshot_t (maintenance endpoint).
esp_err_t rest_api_history_export(void *buffer, size_t *size);
esp_err_t rest_api_history_import(const char *body, size_t size);

#ifdef __cplusplus
}
#endif
