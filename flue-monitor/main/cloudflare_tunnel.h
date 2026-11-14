#pragma once
#include <stdint.h>

typedef enum {
  CLOUDFLARE_STATUS_DISABLED, CLOUDFLARE_STATUS_CONNECTING,
  CLOUDFLARE_STATUS_CONNECTED, CLOUDFLARE_STATUS_AUTH_ERROR,
  CLOUDFLARE_STATUS_NETWORK_ERROR,
} cloudflare_status_state_t;
typedef struct {
  cloudflare_status_state_t state;
  uint32_t connections;
  uint32_t configured_connections;
} cloudflare_status_t;

// Call at boot before starting HTTP; later calls apply saved configuration.
void cloudflare_tunnel_start(void);
void cloudflare_tunnel_get_status(cloudflare_status_t *out);
