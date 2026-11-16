#pragma once
#include <stdbool.h>
#include <string.h>
#include <strings.h>

// Keep device-only WS, OTA, Wi-Fi setup and arbitrary local services private.
static bool cloudflare_route_allowed(const char *method, const char *uri, bool websocket) {
  if (!method || !uri || websocket) return false;
  size_t len = strcspn(uri, "?");
  if (!len || len >= 128) return false;
  char path[128];
  memcpy(path, uri, len); path[len] = 0;
  if (!strcmp(method, "POST")) {
    static const char *paths[] = {"/api/settings", "/api/bosch", "/api/event",
      "/api/refill/test", "/api/refill/allow-tonight", "/api/refill/quiet",
      "/api/auth/login", "/api/auth/setup", "/api/auth/password", "/api/auth/logout"};
    for (size_t i = 0; i < sizeof paths / sizeof paths[0]; i++)
      if (!strcmp(path, paths[i])) return true;
    return false;
  }
  if (strcmp(method, "GET")) return false;
  static const char *paths[] = {
    "/", "/login", "/dashboard.js", "/dashboard.css", "/burn-graph.js",
    "/alpinejs.min.js", "/vendor/uplot.min.js", "/vendor/uplot.min.css",
    "/fonts/caprasimo-400.woff2", "/fonts/figtree-variable.woff2", "/fonts/figtree-400.woff2",
    "/fonts/figtree-600.woff2", "/fonts/figtree-700.woff2",
    "/api/reading", "/api/history", "/api/events", "/api/devices/wifi",
    "/api/settings", "/api/settings/status", "/api/auth/status", "/api/cloudflare/status",
    "/api/refill/status", "/api/bosch", "/favicon.ico", "/flue-icon-stove.svg", "/apple-touch-icon.png",
    "/icon-192.png", "/icon-512.png", "/site.webmanifest", "/startup.png",
    "/service-worker.js", "/loading.html"
  };
  for (size_t i = 0; i < sizeof paths / sizeof paths[0]; i++)
    if (!strcmp(path, paths[i])) return true;
  return false;
}
