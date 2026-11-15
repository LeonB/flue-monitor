# Flue Monitor

Plain ESP-IDF (not ESPHome/Arduino) firmware for the wood stove flue
temperature sidecar, on an **Adafruit ESP32 Feather V2** with an **Adafruit
MCP9601** (K-type thermocouple amp) over STEMMA QT. This folder was a
ground-up rewrite (originally `flue-monitor-idf/`) of an earlier ESPHome
version of this same sidecar; that ESPHome project has since been retired
and removed, and this folder renamed to take its place. See the repo root
`CLAUDE.md` for the bigger-picture project this is one half of (alongside
`../flue-display/`), and this folder's own `CLAUDE.md` for
implementation-specific gotchas.

An onboard **Adafruit BMP581** (pressure/temperature) was originally
alongside it, but has since been physically removed — its ambient
temperature reading was almost a duplicate of the MCP9601's own cold-junction
reading, so it wasn't earning its board space. No BMP581 code remains.

**Status: Milestones 1-7 all done and verified on real hardware** (WiFi +
captive portal + mDNS + OTA; MCP9601 sensor; NVS-backed settings + REST API +
rate/zone regression; WebSocket broadcast, now consumed by `../flue-display/`
instead of it polling REST; Google Sheets logging + woodstove event logging,
both verified against the real production webhook; an embedded web UI --
dashboard, 24h graph, settings, event-log sheet, all served from the device
itself at `/` -- visually verified in a real browser).

## Files

- `main/main.c` — boot sequence: NVS, settings, sensors, WiFi (stored creds or
  captive portal fallback), then either the REST API + OTA (once connected)
  or the captive portal (if not)
- `main/config.h` — compile-time tunables and first-boot setting defaults
- `main/settings.c/.h` — NVS-backed runtime settings (zone thresholds,
  fast-rise rate, deadband, heartbeat, Google Sheets webhook/secret, and
  LED/glow pulse-tuning constants this device itself never reads -- see
  `CLAUDE.md`'s "LED/glow pulse-tuning constants now live in settings")
- `main/sensors.c/.h` — MCP9601 init/read, I2C bus recovery, and the
  rate/zone regression (ported from the ESPHome sidecar's own lambda)
- `main/rest_api.c/.h` — `GET /api/reading`, `GET`/`POST /api/settings`,
  `GET /api/events`, `POST /api/event`, `GET /api/history`, and serves the
  embedded web UI (`main/web_ui/`)
- `main/web_ui/` — the embedded dashboard/graph/settings web UI (HTML +
  Alpine.js + the shared design-system CSS, no build step -- see "Web UI"
  below)
- `main/ws_server.c/.h` — `/ws` broadcast endpoint (reading + settings-changed
  events), registered onto the same shared HTTP server
- `main/sheets_logger.c/.h` — periodic (deadband/heartbeat-gated) + event-
  triggered Google Sheets logging, on its own FreeRTOS task so a slow Apps
  Script response never blocks sensor sampling or the REST/WS servers
- `../components/wifi_setup/`, `../components/captive_portal/`,
  `../components/dns_server/`, `../components/ota_server/` — WiFi credential
  storage (NVS) and the fallback setup access point with a live
  test-connect-before-save flow, and the authenticated `POST /ota` endpoint
  (registered onto `rest_api`'s shared HTTP server -- only one server can
  bind port 80); shared with `../flue-display/` (see the repo root
  `CLAUDE.md`'s "Shared components" section)
- `activate-idf.sh` — sources the cached ESP-IDF 6.0.3 toolchain for the monitor;
  the display retains its separately selected SDK version
- `ota_flash.sh` — pushes a build to a running device over WiFi
- `partitions_ota.csv` — two-OTA-slot partition table
- `google-sheets-logger/` — the Google Apps Script webhook `sheets_logger.c`
  posts to, plus its own setup `README.md`

## Setup

The monitor requires the Feather V2's 2 MiB PSRAM for history, JSON, Bosch,
WebSocket send buffers, settings request bodies and asset decompression buffers.
These application buffers never fall back to internal RAM. The shared allocator
uses internal RAM only in builds configured without PSRAM, such as the display.
Cloudflare tunnel allocations, HTTP/2 session/frame/header buffers and TLS
allocations use strict PSRAM, without internal fallback. Temporary SDK objects,
task stacks, Wi-Fi and DMA allocations remain internal.
Task stacks and ordinary malloc allocations remain internal. SDK code that
explicitly requests generic heap capabilities can still select PSRAM.
Assets themselves stay in flash. Reading telemetry reports both internal RAM
and PSRAM usage. An existing sdkconfig with SPIRAM disabled must be updated
explicitly; sdkconfig.defaults only supplies missing configuration values.

The normal configuration selects `CONFIG_MBEDTLS_CUSTOM_MEM_ALLOC=y`.
`tls_memory_init()` installs the PSRAM-only allocator once, at the start of `app_main`,
before any network workers. This applies to Mbed TLS/PSA allocations, not only
the record buffers. Failed allocation is logged and propagates to TLS without
using internal RAM. Both the active sdkconfig and sdkconfig.defaults select
this policy. Reading telemetry reports `buffer_psram_only` and `tls_psram_only`
so the running policy can be checked after deployment. Do not interpret a
successful build or host allocator test as proof of improved device stability.

`memory.stacks` reports six application tasks (`main`, `sensor`, `sheets`,
`bosch`, `cloudflare`, `http`). Each entry contains `size_bytes`, `min_free_bytes`
and `peak_used_estimate_bytes`. The main loop scans lifetime stack high-water
marks every ten seconds, without an extra task or enabling FreeRTOS tracing.
Unregistered/unmeasured tasks are omitted. Values reset at reboot and estimate
use from untouched stack fill bytes; they are not a guarantee of worst-case use.
Keep stack sizes unchanged until handshakes, reconnects, uploads, authentication
and errors have been exercised. An OTA handler's final peak is lost at its reboot
unless captured separately before restarting. The existing JSONL recorder keeps
the nested stack fields automatically.

The monitor uses ESP-IDF **6.0.3**, which includes Espressif's
[light-sleep/cache-workaround fix](https://github.com/espressif/esp-idf/commit/d45606bf1d450924fbba25eb692ab7d7e27dee77).
The previous custom 5.5.6 backport and SDK tracing copies are removed.
Both interrupt and RTC watchdog protection remain enabled. The interrupt
watchdog is 800 ms; automatic light sleep stays enabled. Feature-isolation
options default off. Sensor and LED driver contexts use internal memory via
their IRAM-safe options. A 30-minute full-feature hardware test passed with
PSRAM and automatic light sleep enabled, live sensor/display data, a confirmed
Sheets upload and 175 successful LAN/public web requests. This bounded test
does not establish long-term stability; see CLAUDE.md for measured results.

```sh
. ./activate-idf.sh && idf.py build                             # build
. ./activate-idf.sh && idf.py -p /dev/cu.usbserial-XXXX flash   # first flash (or after a fresh USB plug-in)
. ./activate-idf.sh && idf.py -p /dev/cu.usbserial-XXXX monitor # serial log (exit with Ctrl+], not Ctrl+C)
```

If the device has no stored WiFi credentials (or they fail to connect), it
starts a setup access point called **"Flue Monitor Setup"** (password
`flue-monitor-setup`) with a captive portal: pick your network from the
scanned list, enter its password, and the device tests the connection live
(while the setup AP stays up) before ever saving anything or rebooting — a
wrong password shows an inline error on the same screen instead of a blind
reboot-and-hope.

## Watchdog diagnostic build

Build the current sources with UART core dumps including registers, task stacks
and explicitly marked recorder data, a dedicated 2048-byte internal core-dump stack, the
FreeRTOS stack-end watchpoint, light heap poisoning and the flight recorder:

```sh
sh tools/build_watchdog_diagnostics.sh --size
```

The script copies the normal `sdkconfig` and applies
`sdkconfig.watchdog-diagnostics.defaults` in an isolated build directory. `--size`
uses size optimization (`-Os`); the ELF retains debug symbols. Omitting it keeps
the normal optimization setting for a size comparison. Both variants retain
the existing OTA partition table, services, PSRAM policy, light sleep, task stack
reservations and 800-ms interrupt watchdog timeout. Neither command flashes.

The size-optimized artifacts are `build/watchdog-diagnostics-size/flue-monitor.bin`
and its matching `flue-monitor.elf`. Preserve that exact ELF with the capture;
the regular `build/flue-monitor.elf` describes a different firmware image.
The normal `ota_flash.sh` selects the regular build, not this diagnostic image.

Continuously record the raw UART at 115200 baud before a failure. The core dump
is emitted automatically without waiting for Enter; retain the complete
`CORE DUMP START` through `CORE DUMP END` block as well as the panic/backtrace
and following boot log. IDF Monitor can decode using the matching diagnostic
build. Full DRAM/heap capture is disabled: it walks heap locks which a halted
CPU may own. The November 1 watchdog dump re-entered panic during that walk.
The diagnostic build rejects that unsafe configuration at compile time.
Registers, task stacks (including the interrupted stack), and the explicitly
marked internal flight recorder remain captured without that heap walk.
Arbitrary heap/PSRAM contents are omitted. A previous controlled abort verified
the older full-heap mode; the new mode still needs hardware crash verification.
Capture still depends on the panic handler and readable memory.

The recorder has 96 operational and 32 sleep records per CPU: 4096 bytes plus
24 bytes of metadata in internal RAM. Separate sleep banks prevent frequent
sleep transitions from overwriting network events. Records contain a committed
sequence, clock, event ID, core, flags and numeric value. Operational clocks
are low 32-bit microseconds (wrap about 71.6 minutes); early sleep callbacks
use CPU cycles instead (flag bit 0), so these clocks are not directly comparable.
No payloads/credentials are recorded. A 528-byte RTC tail is replayed at boot
when its version/commit markers validate; retention is not guaranteed for all
resets or power loss. Sleep callbacks and record writes execute in IRAM with
internal data, brief local interrupt masking and no allocation or spinlock.

ESP-IDF 6.0.3's panic RTC watchdog interrupted the first full UART dump after
about ten seconds. A version-guarded project linker wrapper extends only the
dump interval to at most ten minutes, then restores ten seconds. Runtime
IWDT/TWDT settings are unchanged. Its tick conversion uses 64-bit multiplication
to avoid overflow. Review the private SDK integration when changing IDF.

For a controlled capture test, explicitly build with:

```sh
sh tools/build_watchdog_diagnostics.sh --size --self-test
```

Only that separate image accepts `FLUE_DIAG_CRASH` (abort) or `FLUE_DIAG_WDT`
(interrupt watchdog with a heap lock held), followed by newline on the
physical console. The watchdog test spins inside IDF's heap-walker callback
while its heap lock is held. It never crashes automatically and has no network crash
endpoint. UART receive can miss input during light sleep; normal LAN status
traffic was used to keep it active while sending the test command. After the
test, deploy the ordinary diagnostic image without `--self-test`.

Verify a raw capture locally using the exact self-test image's ELF:

```sh
. ./activate-idf.sh
python tools/verify_flight_dump.py --serial /path/to/serial.raw \
  --elf /path/to/exact/flue-monitor.elf --output /path/to/verification
```

The verifier checks the SDK checksum, exact stack patterns and
committed recorder entries (including ring wrap and sleep events). Raw dumps
contain application memory and should stay local; its JSON report prints only
verification results. The final diagnostic image omits the test task/markers.
Use `--expect-heap` only for archived full-heap self-test captures. This tool
requires deliberate test markers; it is not an acceptance test for real crashes.

On 2026-11-01 the `FLUE_DIAG_WDT` hardware test produced a complete,
checksum-valid dump: known stack markers and102 recorder entries verified,
and the official6.0.3 decoder identified the test task inside the held-lock
callback. No nested panic occurred. Capture/ELF/decoded report are archived
in `.cache/watchdog-captures/controlled-iwdt-20261101/`. This verifies that
specific watchdog/held-lock scenario, not every possible panic failure.

## Updating over WiFi (OTA)

```sh
cp main/secrets.h.example main/secrets.h   # first time only -- fill in a real random string
. ./activate-idf.sh && idf.py build
./ota_flash.sh <device-ip-or-hostname>     # e.g. flue-monitor.local
```

`main/secrets.h` is git-ignored; the same secret has to be in it on every
machine that pushes updates.

The monitor's OTA script first downloads graph samples and event annotations
to `.cache/ota-history/<timestamp>/history-before.json` on the Mac. Each sample
and event has an absolute UTC Unix timestamp in seconds (`timestamp`), anchored
to the Mac's capture time (`captured_at`). After flashing
and restarting, it restores them to RAM and verifies them by reading them back.
The backup and firmware copy remain on the Mac if an update fails. No graph
snapshot is written to device NVS. A failed backup stops the script before upload.
The saved UTC timestamps stay unchanged during restore. Relative ages are used
only for transport to the existing firmware, whose sampling clock is monotonic;
device NTP changes do not alter the Mac backup. Raw `.bin` captures are retained
alongside the JSON for diagnostics. The capture-time mapping has approximately
one-second rounding plus network-delay uncertainty; it is not subsecond timing.

For an explicit image, or an update without a graph backup:

```sh
python3 tools/ota_with_history.py . flue-monitor.local --image build/flue-monitor.bin
python3 tools/ota_with_history.py . flue-monitor.local --without-history
```

USB recovery uses the same backup/restore flow with `--usb-port PORT` and
`--expected-mac MAC`. It checks device identity and the partition layout before
writing only the two application slots; settings, bootloader and partition table
are preserved. Activate ESP-IDF first so `esptool` is available. The monitor must
still be reachable over WiFi to download the backup before the USB reset.

PNG assets can be optimized losslessly with `tools/optimize_png_assets.py`.
This optional maintenance tool needs Pillow and zopfli; neither is needed for
normal builds. Run without arguments to measure, or with `--write` to apply only
changes that shrink the actual gzip payload embedded in firmware. It verifies
identical RGBA pixels, dimensions and color metadata, and archives originals
under `.cache/asset-optimization/`.

## REST API (once connected to WiFi)

Reading responses and device WebSocket readings include a `memory` object
with internal byte-addressable free RAM, allocator low-water bytes, largest
free block, and sampled largest-block minima. Sampling runs every 100 ms
in the existing main task and on Sheets HTTP events, without an extra task.
Sheets attempt/completion/success counters and Cloudflare connection state
help interpret measurements. Byte counts are RAM, not flash. Sampled minima
can miss shorter peaks; allocator low-water bytes sum the individual heaps'
historical minima. Zero Sheets minima mean no request has been sampled yet
(check `sheets_attempts`). These diagnostics do not change API authentication.

```sh
curl http://flue-monitor.local/api/reading
curl http://flue-monitor.local/api/wifi       # live SSID/BSSID/channel/RSSI, not cached
curl http://flue-monitor.local/api/settings
curl -X POST http://flue-monitor.local/api/settings \
  -H "Content-Type: application/json" \
  -d '{"log_heartbeat_min":15,"zone_cold_max_c":150,"zone_optimal_max_c":280,"fast_rise_c_per_min":20,"thermocouple_deadband_c":5,"google_sheets_webhook_url":"","google_sheets_secret":"","idle_pulse_period_ms":8000,"fast_pulse_period_ms":1400,"rate_deadband_c_per_min":3,"color_transition_exponent":3,"zone_cold_color":"#003cff","zone_optimal_color":"#ff3700","zone_hot_color":"#ff0000","breathing_exponent":1,"minimum_brightness":20,"maximum_brightness":255}'
```

`POST /api/settings` replaces the whole settings object (no partial/PATCH
semantics) and validates before persisting — an invalid payload (e.g.
`zone_cold_max_c >= zone_optimal_max_c`) gets a `400` and leaves the stored
settings untouched. On success, it also broadcasts `{"type":"settings_changed"}`
over `/ws` (see below). The three `zone_*_color` fields accept exactly
`#RRGGBB`; older clients can omit them to preserve the saved colours.

## Cloudflare remote access

In Cloudflare, create a remotely managed tunnel and a **Published application**
for your hostname, with service `http://localhost:80`. In the monitor's
**Settings → Cloudflare Tunnel**, enter the same public hostname and connector
token, choose 1–4 connections, enable Remote access and Save. Use the connector
token, not a Global API Key or API token. Tokens are never embedded in firmware.

The token is write-only: settings return `cloudflare_token_set`, never the token.
Blank or omitted tokens preserve the saved value. Configuration persists in NVS;
saving reconnects gracefully, and disabling closes the tunnel while retaining
its configuration. Old settings (including reverted panel layouts) retain their
sensor/display/Sheets values; Cloudflare starts disabled and needs configuration.
The new blob uses `settings_v2`; `settings_v1` is retained for app rollback.
The PageKite client is no longer built. Its old blob tail exists only for NVS
compatibility and is never exposed or used for connections.

Public requests are restricted to the configured HTTPS hostname and dashboard
route allowlist. Assets and API responses are served directly over HTTP/2,
without loopback sockets or another HTTP/1.1 parser. The same application
handlers and authentication run on the shared HTTP task for both transports.
Captured headers, bounded bodies and response data use PSRAM; the small atomic
control blocks stay in internal RAM. Flash assets stream in 512-byte chunks;
clients without gzip use the existing ROM inflater with a PSRAM dictionary.
At most 16 direct requests are pending, with a 10-second handoff deadline.
Cookie, Origin and asset-version checks are shared with LAN handling. OTA,
Wi-Fi setup and the LAN device WebSocket remain private. The display's LAN
connection is unchanged.

The embedded dashboard asks you to choose a password on first use; do this
from the monitor's home-network address. Initial setup is blocked through
Cloudflare so a remote visitor cannot claim a fresh device. It protects the
dashboard assets and REST endpoints over LAN and Cloudflare. Unauthenticated
LAN GET /api/settings remains available without credentials for flue-display;
local commissioning saves are allowed only until the first password is set. The password is
stored in NVS as a salted PBKDF2-HMAC-SHA-256 hash; the settings API never
returns it. Change it in **Settings → Dashboard access**; the current
password is required and the new password must be confirmed. Up to eight independent
browser sessions can remain active, for example desktop, iPhone and curl.
Signing out ends only the current session; when all eight slots are occupied,
a new login replaces the least recently used session. Without Keep me signed
in, each session uses a browser-session cookie (no expiry date).
Browsers may preserve session cookies when restoring a previous session. Remembered sessions
have no server time limit and end on monitor restart. Five failed sign-ins
cause a 30-second lockout. Password changes invalidate all sessions.
Remote cookies are Secure and all remote state-changing requests require
a matching HTTPS Origin. The device WebSocket used by flue-display remains outside dashboard
authentication. The local proxy preview in
`tools/ui_proxy.py` remains a design prototype and does not secure the device.

USB-serial password recovery is not implemented yet. A normal app-only flash
preserves NVS and therefore will not reset the password; a full flash erase
clears all NVS settings and is not the intended recovery method. The web
interface uses HTTP on the local network, so a password entered over plain
LAN HTTP can be observed by someone able to monitor that network traffic.

`GET /api/cloudflare/status` reports `state`, active `connections` and
`configured_connections`, without credentials. A connected edge does not prove
end-to-end public reachability. The Settings page refreshes status while open.

Settings fields: `cloudflare_enabled` (boolean), `cloudflare_hostname` (bare
hostname, maximum 127 characters), `cloudflare_connections` (integer 1–4),
write-only `cloudflare_token` (maximum 4095 characters) and read-only
`cloudflare_token_set`. Omitted fields preserve saved values. These monitor-only
settings do not wait for a display acknowledgement.

The library revision and local changes are in `components/esp_cf_tunnel/UPSTREAM`.
TLS/PSA, tunnel data and HTTP/2 sessions use strict PSRAM allocation; stacks stay
internal. Four connections still require hardware qualification with PSRAM and
the full monitor workload. The no-PSRAM S3 prototype ran out of memory with four.
Size optimization, link optimization scoped to the two protocol libraries, and
build-time gzip of the unchanged login template keep the existing OTA partitions.

Host checks: `tools/test_cloudflare_settings.py`, `tools/test_cloudflare_tunnel.py`,
`tools/test_cloudflare_memory.py`, `tools/test_login_compression.py`, and
`node tools/test_settings_sync.js`. These do not establish device stability.
`tools/test_direct_http2.py /path/to/miniz-v114.c` exercises the actual adapter,
bridge and authentication under ASan/UBSan, including cancellation, timeouts,
allocation failure and multi-block identity streaming. The upstream miniz
reference supplies the ESP32 ROM tinfl API for this host test.

## Woodstove event logging (once connected to WiFi)

```sh
curl http://flue-monitor.local/api/events   # the fixed taxonomy: [{"slug":"cold_start","label":"Cold Start"}, ...]
curl -X POST http://flue-monitor.local/api/event \
  -H "Content-Type: application/json" \
  -d '{"event":"cold_start"}'
```

`POST /api/event` logs an immediate, un-gated Sheets row (see "Google Sheets
logging" below) for one of the fixed event slugs `GET /api/events` lists --
an unknown slug gets a `400`. No web UI exists yet to tap these from a
phone at the stove (Milestone 6); for now this needs a raw HTTP client.

## WebSocket broadcast (once connected to WiFi)

```sh
# any WS client, e.g. `websocat ws://flue-monitor.local/ws`
```

Broadcasts `{"type":"reading","reading":<same shape as GET /api/reading>}`
every ~30s (matching the sensor's own update cadence), and
`{"type":"settings_changed"}` immediately after a successful
`POST /api/settings` — `flue-display` uses this instead of polling REST, and
re-fetches `/api/settings` on the latter event.

## Web UI

Open `http://flue-monitor.local/` — a dashboard (a glowing circle mirroring
`flue-display`'s own LED ring, pulsing zone-color/speed via the same math
ported from `led_display.c`), a 24h graph, and a settings page, all one
embedded HTML/Alpine.js page (`main/web_ui/`, no build step, REST-polled
every 5s — WS is reserved for the `flue-display` link, not this human-facing
UI). The event-log bottom sheet uses the same `GET /api/events`/
`POST /api/event` as any other client. Settings edits use a draft/Save-bar
pattern (nothing is sent until you tap Save). Cold, Optimal, and Hot colour
pickers control the dashboard glow, graph bands, and physical LED ring.
Defaults are blue (`#003cff`), amber (`#ff3700`), and red (`#ff0000`).
Both devices need this firmware update for the ring to use the saved palette.

```sh
curl http://flue-monitor.local/api/history
```

Backs the 24h graph: `{"now_s": <uptime>, "samples": [[age_s, temp_c, rate,
zone_code], ...], "events": [[age_s, slug], ...]}`, oldest first,
downsampled to ~4min resolution (360 points for 24h — a phone-width graph
has no use for the sensor's raw ~30s cadence, and `zone_code` is a raw
numeric 0-3, unlike `GET /api/reading`'s string `thermocouple_zone` — see
`rest_api.c`'s own comment on why these two endpoints differ).

### Iterating on the web UI without a real device

```sh
python3 tools/mock_server.py        # then open http://localhost:8000/
```

Serves the real `main/web_ui/` files as-is (no copies, no build step) with
a synthetic ~24h burn curve and a couple of seeded events standing in for
the REST API — `GET`s return fake-but-plausible data, `POST /api/event`/
`POST /api/settings` are accepted and reflected back by later `GET`s, so
the full dashboard/graph/settings flow works end to end, including
tapping a real event button and immediately seeing it land on the graph.
No flashing, no reboot, no real device needed for CSS/layout/JS changes —
only reach for a real flash-and-check once a change also touches the
firmware side (a new REST field, a new settings key, etc.).

## Bosch EasyControl room temperature

Settings → **Bosch room temperature** connects a CT200 through the POINTT
cloud API. Click **Connect to Bosch**, open the generated SingleKey ID link,
and paste the complete `com.bosch.tt.dashtt.pointt://app/login?code=…&state=…`
callback into **Bosch return link**. In Firefox, enable Network → Preserve log
before signing in and copy the final redirect's `Location` response header.
The browser's unknown-protocol error at that point is expected. Links belong
to one sign-in attempt and expire after 20 minutes or a monitor reboot.

The main room normally uses `zn1`. Room zone is a dropdown populated from the
thermostat’s `/zones` references (cached for ten minutes). The current selection
remains available while discovery is pending or offline. With exactly one gateway it is discovered
automatically. With multiple gateways, enter the desired serial number without
spaces and save the selection. The dashboard displays the selected room
separately from the flue sensor; it does not alter stove classification,
history or display lighting. Each Sheets upload also includes the current
room temperature; see `google-sheets-logger/README.md` for the script update.

The worker polls once per minute, refreshes tokens before expiry and after
reboot, retries transient failures with 30–900 second backoff, and requests
sign-in again on rejected refresh credentials. Values outside -40…60 °C
(including the CT200's observed `1000` sentinel), failed reads and samples
older than three minutes are unavailable. Requests never write heating settings.

`GET /api/bosch` returns status, freshness, selected device/zone, counters and
an active sign-in URL. `POST /api/bosch` accepts `action` values `start`,
`callback` (with `callback`), `select` (with `device` and `zone`) and `disconnect`.
POST returns 202 for queued work; poll GET for completion. Both methods require
a dashboard session; POST also requires the matching Origin. Both are available
through Cloudflare. Tokens and authorization codes are never returned by the API,
settings or device WebSocket. The pending sign-in URL contains only public OAuth
parameters; its PKCE verifier remains private on the monitor.

The refresh token and selection are one record in the separate `bosch` NVS
namespace. Access tokens remain in RAM. **Disconnect** removes the local
credentials; it does not revoke Bosch-side grants. NVS is not encrypted in the
current firmware, and the LAN dashboard still uses HTTP. Use the HTTPS dashboard
for pairing where possible. This is an unofficial integration using the Bosch
app's client ID, based on [ha_bosch](https://github.com/CaseyRo/ha_bosch).

Host checks: `python3 tools/test_bosch.py`, `node tools/test_bosch_ui.js` and
`python3 tools/test_cloudflare_tunnel.py`. The mock server simulates pairing and an
invalid `zn2` reading without contacting Bosch. Hardware pairing and live room-temperature display have been verified. Long-running
token refresh, restart recovery and Bosch-specific peak memory still need a longer soak.

## Google Sheets logging

Configure `google_sheets_webhook_url`/`google_sheets_secret` via
`POST /api/settings` (see above) to enable. Once set, `sheets_logger.c` logs
a row on its own ~30s-tick task whenever either is true:

- **`temp_change`**: the thermocouple reading has moved by at least
  `thermocouple_deadband_c` since the last logged row.
  - **`heartbeat`**: at least `log_heartbeat_min` minutes have passed since
    the last logged row, regardless of delta.

The dedup baseline (`s_last_logged_thermocouple_c`) is in-RAM only, not
NVS-persisted, so a reboot always logs one row immediately on the first tick
— matching the ESPHome sidecar's own `restore_value: false` behavior.
`POST /api/event` (see "Woodstove event logging" above) logs a fourth kind
of row, tagged with one of the fixed event slugs instead of `temp_change`/
`heartbeat` -- immediate and un-gated, bypassing the deadband/heartbeat
check entirely and not resetting either's clock.

## Onboard NeoPixel: WiFi status at a glance

`status_led.c` drives the board's onboard NeoPixel as a solid color
reflecting the WiFi connection lifecycle: **amber** while attempting to join
stored credentials, **green** once connected (REST/WS/OTA all up), **red**
while the setup access point / captive portal is active. Shares its
power-enable line with STEMMA QT (GPIO2, already driven high by
`sensors_init()` before this ever runs) — see `CLAUDE.md`.

## Hardware notes

| Function              | Pin/value |
|------------------------|-----------|
| STEMMA QT SDA          | GPIO22 |
| STEMMA QT SCL          | GPIO20 |
| STEMMA QT power        | GPIO2 (must be driven HIGH — see `CLAUDE.md`) |
| Onboard NeoPixel data  | GPIO0 (WiFi status color, see above) |
| MCP9601 I2C address    | 0x67 |
| I2C bus speed          | 50kHz (see `CLAUDE.md`'s MCP960x errata notes) |

Breathing shape under **The pulse** adjusts the brightness envelope of both the
UI halo and LED ring (0.3–3.0, default 1.0). Lower values stay bright longer;
higher values stay dim longer. The colour-transition curve remains independent.

Minimum and maximum brightness under **The pulse** set the LED ring’s trough
and peak on a 0–255 scale, in steps of 5. Defaults are 20 and 255. Minimum
cannot exceed maximum; equal limits give steady brightness, and both zero
turn the ring off. These controls affect the ring, not the screen halo.

The **Theme** selector under **The zone** offers Classic, Fire (yellow/amber/red), Ember, Forest and
High contrast palettes with previews in cold/optimal/hot order. Selecting a
theme fills the three colour pickers; Save applies it and Undo restores the
saved palette. Any combination that does not match a preset shows Custom.

## Naming and coordinated rename inventory

The visible product names are **Flue Monitor** and **Flue Display**. The dashboard, login page, setup Wi-Fi names and device discovery now use
Flue. The local repository/folders and build names are also renamed. Configured public
domains still use the old identifiers.

| Area | Current → intended | Coordination required |
| --- | --- | --- |
| Device discovery (implemented) | `flue-monitor.local`; `flue-display.local` | Change monitor `main/config.h` `MDNS_HOSTNAME`, monitor `main/main.c` instance name via that macro, display `main/config.h` `FLU_MONITOR_MDNS_NAME`, and display `main/flue_poll.c` hostname/instance. Deploy monitor first by confirmed IP (the running display retains its resolved IP), then deploy the display to resolve the new name. Verify settings fetch, WebSocket reconnect and acknowledgements. Update bookmarks and local proxy targets. |
| Setup Wi-Fi (implemented) | `Flu Monitor Setup` → `Flue Monitor Setup`; `Flu Display Setup` → `Flue Display Setup` | Both `main/config.h` files and both device READMEs. Setup passwords in source are now `flue-monitor-setup` and `flue-display-setup`; deployed firmware keeps its previous password until flashed. |
| Public domain | `flumonitor.vanutsteen.nl` → `fluemonitor.vanutsteen.nl` | Create the Cloudflare published application and its tunnel CNAME, then configure the same hostname on the monitor after deployment. New hostname means a separate browser cookie. Keep the old address during cutover where routing supports it. |
| Legacy PageKite name | `flumonitor-vanutsteen.pagekite.me` | Historical production address. The Cloudflare integration removes this client; existing deployed firmware and external routing are unchanged until a separate cutover. |
| Repository and folders (implemented locally) | `LeonB/flue-monitor`, `flue-monitor/`, `flue-display/` | GitHub repo renamed by owner; origin and local checkout/subfolders updated. Relative paths and documentation links updated. Ignored credentials preserved. Reopen IDE/Codex at the new checkout path. |
| Build and OTA artifacts (implemented locally) | `project(flue-monitor)` / `project(flue-display)` | Regenerate both builds after moving folders. The shared root `ota_flash.sh` derives the `.bin` name from the project folder. Old generated builds are archived under `/tmp/flue-monitor-rename-builds-20261016`; no partition/NVS reset. |
| Internal references | `FLU_MONITOR_MDNS_NAME`, `FLU_DISPLAY_TEST_WS_URI`, PageKite client-version string, demo domains and temporary filenames | Update source and build/test scripts together. Preserve historical diagnostic references where useful. These can remain compatibility names until the network/build cutover is complete. |

Keep the session cookie `flu_session`, preview cookie `flu_auth_preview`, NVS
namespaces/keys, API paths and WebSocket payload fields stable: renaming them
is unnecessary for branding and can invalidate access or persisted settings.
Before cutover, inventory deployed settings without exposing secrets and record
rollback domains/hostnames. Verify both devices by known IP and identity,
including thermocouple readings, display settings acknowledgement, public
HTTPS login and OTA. Public domain names above are proposed, not registered
or verified by this inventory.
