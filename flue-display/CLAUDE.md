# Flue Display implementation guidance

Plain ESP-IDF **6.0.3**, not ESPHome/Arduino. Read `../CLAUDE.md` for shared
components and device identity, and README.md for build, wiring and OTA commands.
Previous milestones, LED trials and deployment chronology are retained verbatim
in [development history](docs/development-history.md). Older SDK, ring and
resolve-only-once descriptions there are historical.

## Build and dependencies

Source `. ./activate-idf.sh` in the same command as `idf.py build`. Both projects
use the existing cached SDK 6.0.3 and its Python environment. cJSON is a managed
component in IDF6. Keep managed sources and the SDK untouched.

CMake generates a checked local WebSocket-client copy to reject redirects
without leaking handshake sockets. Preserve source-shape guards; dependency
updates require reviewing that workaround. Never remove it merely because a
build succeeds. Hardware fault injection uses explicit `FLU_DISPLAY_TEST_WS_URI`;
production must leave it empty. Do not redirect diagnostic traffic to production.
A successful build does not establish deployment or electrical stability.

## Hardware and rendering

Lolin D32 Pro; GPIO13 drives a 64-pixel Adafruit 1487 8x8 **SK6812 RGB** matrix.
Use `LED_MODEL_SK6812`, three-channel GRB and `led_strip_set_pixel`. Do not send
RGBW frames. Every pixel has the same colour, so serpentine layout is irrelevant.
GPIO5 onboard status LED is active-low. Keep the separate hardware-specific LED
implementation; it cannot be replaced by the monitor's NeoPixel status driver.

Create RMT inside the render task pinned to core 1, with 256 symbols. Original
ESP32 has no RMT DMA; do not enable it. Keep real elapsed-time pulse integration,
absolute scheduling and overrun handling. Gamma 2.8 is applied after colour
interpolation and before global brightness; neutral no-data white uses equal RGB
without gamma. This is a visual tuning choice, not a measured panel calibration.
Physical colours/flicker require owner observation; FPS/refresh success cannot
prove signal integrity. Check supply, grounds, cable and level shifting when
investigating electrical symptoms.

## Network and settings

WiFi setup, live test-connect-before-save and reconnect are shared components.
The SoftAP is Flue Display Setup. Plain `.local` resolution through the HTTP
client is unreliable: use explicit mDNS discovery. Failed discovery leaves the
existing address/auto-reconnect intact; sustained unhealthy operation refreshes
mDNS and WS after 60s. HTTP settings fetch and WS must use the same fresh IP.
Stop/restart WS outside its callback. Keep frame reassembly, contiguous-offset
checks and 2048-byte bound; never parse truncated JSON.

Refresh settings on WS connect/reconnect/change, retry failed fetch/ack after 5s,
and refresh every 30s. Apply valid tuning/palette before sending the exact
`settings_applied` revision; never acknowledge a failed fetch. Preserve fallbacks
for older sidecars. Do not dump a failed settings response to logs: it can contain
credentials. Independent RSSI reports use the existing WS every 10s, without new
sockets or waiting for blocking settings fetches.

## Reading acceptance and OTA

Keep -40..600°C plausibility, pending-jump confirmation and staleness handling.
Confirmation must accept sustained trends and stable plateaus, reject isolated
spikes and reversals. Plausible-stream freshness is separate from display-value
acceptance; protect shared state with the existing critical sections.

OTA remains LAN-only with its existing secret/rollback behaviour. Verify device
identity before flashing; the monitor and display can both boot the wrong
firmware. Clear fault-test overrides and check the final binary before any
production deployment. Do not claim hardware validation from host tests.
