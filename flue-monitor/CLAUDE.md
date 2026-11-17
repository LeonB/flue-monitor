# Flue Monitor implementation guidance

Plain ESP-IDF **6.0.3**, not ESPHome/Arduino. Read `../CLAUDE.md` for shared
boundaries and device identity, and README.md for commands and API usage.
All development/deployment chronology is preserved verbatim in
[development history](docs/development-history.md). Historical pending work,
old SDK versions and retired tunnel instructions are not current requirements.

## Build and verification

Source `. ./activate-idf.sh` in the same command as `idf.py build`.
The activation script selects the existing ESPHome SDK cache and its Python
environment. Do not modify the SDK or managed components directly. The checked
IWDT transition patch is applied through CMake; its instruction ordering, IRAM
and internal-memory requirements are deliberate. Watchdog tests are separate
from normal builds; do not restart monitoring, run crash tests or flash hardware
without authorization. The 2026-11-17 cleanup is deployed; see development history for verification.

Firmware must fit the existing 1,536,000-byte OTA slots. Ordinary application
buffers and cJSON allocations are strict PSRAM on the monitor; no internal-RAM
fallback. DMA, task stacks and ESP32 atomic control objects remain internal.
Keep measured stack reservations; successful compilation is not evidence that
stacks or electrical behaviour can be changed safely. Registration of stack
telemetry must not abort boot; registered tasks must stay alive or unregister.

## Hardware and sampling

GPIO2 powers STEMMA QT and the onboard NeoPixel: drive it high before I2C.
Recover the I2C bus on every boot with clock-stretch-aware pulses and STOP.
Keep MCP960x bus frequency and pull-ups as configured; errata previously caused
plausible but wrong/stale readings. BMP581 is physically removed.

Only the sensor task calls `sensors_read()`, at the true ten-second cadence.
GET/WS consumers use the cached reading. Plausibility is -40..600°C; invalid
samples must not poison regression or logging baselines. Regression spans 150s.
Graph sampling is every four minutes, 360 points, retaining stable-run endpoints
by anchored comparisons. Compression during import may remove additional
redundant points. Do not claim exact point retention from graph equivalence.

## HTTP, authentication and assets

One normal HTTP server shares REST, local OTA and device WS. Setup portal runs
instead of it. Application handlers for LAN and direct Cloudflare HTTP/2 execute
on the same HTTP task through `web_request`; only the tunnel task touches CFT
streams. Request bodies are bounded; incomplete/timeout reads terminate an
application request. OTA streams separately with bounded timeout retries.

Keep the explicit tunnel method/path allowlist; never expose OTA, WS, setup or
arbitrary LAN services remotely. First password enrollment is LAN-only. Keep
session auth, Origin/CSRF checks and secret redaction across both transports.
Remembered sessions have fixed 90-day expiry, eight slots, hashed cookies in
RAM/NVS and credential binding. Logout/rotation/eviction must persist before
success; failure rolls back. Unsynced clock checks must not erase sessions.
Normal authenticated requests neither renew cookies nor write NVS.

Assets have one gzip payload and identity fallback, representation-specific
ETags and identity-content version hashes. Preserve old font aliases, uppercase
V font queries on the tunnel, all launch-image URLs and service-worker behaviour.
SDK embedding symbols collide on basename. Dashboard JS must load before Alpine;
Alpine invokes `init()` itself. The worker caches only public loading HTML,
never authenticated HTML/API data. Preserve login AutoFill semantics; simulated
browser checks cannot establish actual iPhone behaviour.

## Settings and display

NVS `settings_v5` is an append-compatible blob; v1..v4 migrations preserve
credentials and skip the retired tunnel region. Retain old keys for rollback.
Validate before writing NVS or changing runtime state. Validate JSON numbers
before narrowing to float/integer; all persisted float fields must be finite.
Older scalar tuning fields become zero if omitted. Later palette/shape/brightness,
Cloudflare, session-end and refill fields retain stored values for older clients.
Omitted Sheets credentials retain; explicit empty Sheets strings clear. Blank
Cloudflare/refill credentials retain. Preserve those API compatibility rules.

Device settings must not contain Sheets or Bosch credentials, ntfy destination
or tokens. Cloudflare tokens are write-only. Display acknowledgement is tied to
the exact boot-randomized settings revision. UI must distinguish save failure
from saved-but-unconfirmed delivery; monitor-only saves do not wait for display.

## History, events and integrations

History is RAM-only; do not reintroduce graph NVS writes or an OTA checkpoint
veto. Mac UTC backups are immutable; restore converts timestamps to relative
ages. Preserve duplicate event taps, timestamps and append-only taxonomy IDs
(Coaling is ID 10). Local event capture succeeds even when the Sheets queue is
full: report that Sheets delivery was dropped, without inviting duplicate taps.

Sheets events capture sensor/Bosch snapshots at tap time. Prefer synchronized
absolute timestamps; relative age fallback cannot remove network latency.
Only an actual HTTP200 `ok` acknowledgement advances the periodic baseline;
redirect bodies and chunked delivery must be handled correctly. Do not log
secrets or fabricate production events to test a UI/integration.

Bosch workers are read-only cloud consumers with separate room/outdoor validity.
Keep credentials outside device settings/WS; callback state/PKCE, finite values,
expiry and gateway invalidation are required. Notification HTTPS uses the
existing Sheets worker, one pending job and one transport attempt, no ambiguous
retry duplicates. Overheat jobs outrank refill/test and bypass refill enable,
quiet time and manual actions. Refill candidates require measured warming and
cooling; actions alone cannot arm. Below-threshold cold expiry is configurable.
Clock/quiet handling uses the compact current EU DST rule to fit OTA; legislation
changes require review. Status distinguishes ntfy acceptance from phone display.

The graph session framing and raw-sample refill detector intentionally differ.
Sparse Sheets records and interpolated replays are not raw-sample ground truth.
Maintain graph live-follow through deferred uPlot commits while preserving manual
zoom. Verify browser-visible changes in a real browser when layout is affected.
