# Flue Monitor repository

Two plain ESP-IDF firmware projects share WiFi setup, captive portal, DNS, OTA
and flight-recorder components in `components/`:

- `flue-monitor/`: ESP32 sidecar with MCP9601 thermocouple, rate/zone processing,
  RAM graph history, dashboard REST API, display WebSocket feed, Google Sheets
  logging, Bosch temperatures, ntfy notifications and Cloudflare remote access.
- `flue-display/`: Lolin D32 Pro with a 64-pixel SK6812 RGB 8x8 NeoMatrix on
  GPIO13. Shows temperature/trend with colour and breathing; receives `/ws`
  and fetches credential-free tuning from the monitor.

Read each project's `CLAUDE.md` before working there. Day-to-day commands and
API documentation are in its README. Both projects use **ESP-IDF 6.0.3**;
source the project's `activate-idf.sh` in the same shell as `idf.py`.

## Current behaviour

Sensor samples arrive every ten seconds; rate uses a 150-second regression.
The graph retains four-minute samples with stable-run compression, so its
360-point capacity can span more than 24 hours. Event IDs are append-only.
History is RAM-only; monitor firmware updates use Mac-owned UTC backup,
flash, restore and independent readback through `tools/ota_with_history.py`.

Notifications are implemented: an ntfy high-temperature warning strictly above
200°C (rearms below 190°C), plus configurable refill reminders and quiet hours.
Refill detection uses sustained measured warming or measured recovery after a
logged start/refill, then sustained cooling. Settings and remembered dashboard
sessions persist in NVS. See project guidance for details and limitations.

Data collection and threshold calibration continue. Current detection policies
are design choices, not proof of calibrated stove safety. Probe response changes
with thermal contact/mass: recalibrate when replacing the bare-wire stand-in
with the intended clamp probe. Do not deliberately overfire to collect examples.

## Shared component boundaries

`wifi_setup`, `captive_portal`, `dns_server` and `ota_server` are shared.
Setup AP names remain device-specific; the portal page is intentionally neutral.
STA joins use all-channel scanning and strongest-signal AP selection; this is
connection-time selection, not a roaming policy.

Status LEDs have different hardware and retain separate implementations.
Display C and dashboard JS pulse math deliberately remain separate; both obtain
live tuning constants and palette from the monitor. Screen halo brightness and
physical LED gamma are intentionally different.

## Device identity and deployment

A wrong-device flash can boot successfully while silently losing device-specific
functionality. Verify board identity before accessing an unfamiliar serial port
or flashing; USB numbering and mDNS names are insufficient evidence.
Known monitor MAC: `8c:94:df:0b:be:fc`; usual LAN IPs are monitor `.137`,
display `.138`. Verify actual identity rather than assuming DHCP addresses.
Do not open/reset the display port while diagnosing the monitor.

Preserve NVS, bootloader, partition table and OTA selection during monitor
app-only recovery. Use history-preserving update tooling for monitor updates;
never retry an ambiguous mutating request automatically. Builds and host tests
do not establish hardware behaviour or authorize a deployment.

## Historical context

The ESPHome sidecar, BMP581 and PageKite implementation have been retired.
Old milestones, experiments and deployment observations are retained in
[development history](docs/development-history.md); they are historical evidence,
not current operating instructions. Project histories retain diagnostic detail.
