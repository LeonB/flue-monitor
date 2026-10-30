# Google Sheets logger

`Code.gs` is a Google Apps Script webhook that appends flue-monitor sensor
readings to a Google Sheet. It's a template: deploying it happens in your own
Google account, not from this repo.

Columns are matched by header name, never by fixed position. Existing rows and
headers are left in place; missing columns are appended. Legacy field names
keep their readable labels (for example `thermocouple` → `Thermocouple (C)`).
Other query parameters automatically become columns with their exact key as
header. Do not rename those headers: the original name would be added again.

## Adding future fields

Add a URL-encoded query parameter in the firmware, such as `humidity=45.6`.
The script creates a `humidity` column on the first upload and leaves it blank
in uploads without that field. No Apps Script edit or redeployment is needed.
Keys must match `[a-z][a-z0-9_]{0,63}`. `secret`, `event_ts` and `age_ms` are
reserved transport fields and are never logged as additional columns.
Finite decimal numbers are stored as numbers, empty values as empty cells,
and other values as literal text (not formulas). Future fields should send
an empty value when unavailable and validate physical ranges in the firmware.
Known temperature fields retain their existing validation and display formats.
New fields use Sheets' default formatting; units can be included in the key
(e.g. `humidity_pct`). Keep field keys stable to avoid redundant columns.
The firmware still needs enough URL buffer space for any additional data.

A script lock protects header discovery and append against concurrent uploads.
One update of the existing Apps Script deployment is required to enable this
generic handler; preserve its secret and deployment URL.

## Deploy it

1. Create a Google Sheet (any name), or reuse the existing one from the old
   ESPHome sidecar's deployment -- a tab named `Sensor Log` is
   created automatically on first write if it doesn't already exist.
2. In the Sheet, go to **Extensions -> Apps Script**, delete the placeholder
   code, and paste in `Code.gs`.
3. Replace `SHARED_SECRET` in the script with your own random string, e.g.
   generate one with `openssl rand -hex 16`. This is the only thing standing
   between "anyone with the URL" and your sheet, since the deployment step
   below uses the simplest access model.
4. **Deploy -> New deployment**, type **Web app**. Execute as **Me**, access
   **Anyone**. Deploy, and authorize it when Google prompts you to.
5. Copy the resulting URL (ends in `/exec`).

## Wire it into the sidecar

Unlike the old ESPHome sidecar (compiled-in via `secrets.yaml`), this
project's settings are runtime/NVS-backed -- set both values via
`POST /api/settings` (see the repo root's own `README.md` for the full
request shape):

```sh
curl -X POST http://flue-monitor.local/api/settings \
  -H "Content-Type: application/json" \
  -d '{..., "google_sheets_webhook_url":"https://script.google.com/macros/s/XXXXX/exec","google_sheets_secret":"<the random string from step 3>"}'
```

See `main/sheets_logger.c` for how these get sent as a GET request with
query parameters, on its own FreeRTOS task. It's GET rather than POST
deliberately: Apps Script Web Apps always respond with a redirect to a
`script.googleusercontent.com` URL that only accepts GET, and the ESP32's
HTTP client (`esp_http_client`) preserves the original method across that
redirect instead of downgrading to GET, so a POST body fails there with an
HTTP 405 even though it can look fine from a browser or a plain `curl -L`.

## Expect occasional failures -- this is normal

Google Apps Script Web Apps have real, unpredictable latency. Direct `curl`
testing against the deployed webhook showed round trips anywhere from 1.5s to
40+ seconds (timing out) across a handful of back-to-back calls, from a
regular machine on a fast connection, nothing device-specific about it. Two
consequences:

- **A logged timeout/connection failure usually isn't a lost row.** Apps
  Script executes the handler function and writes to the sheet *before* it
  sends the client a response/redirect. If the ESP32 (or curl) fails to
  follow that response chain in time, the write has typically already
  happened. This does *not* apply to a `404` specifically, though --
  observed once live (a scheduled heartbeat log), and a direct `curl -L`
  retry against the same URL immediately afterward succeeded cleanly
  (`302 -> 200 "ok"`), confirming the deployment itself was fine and this
  was a one-off, transient Google-side routing hiccup, not a dropped
  request the row still landed from. Check the sheet before assuming either
  way.
- **`sheets_logger.c` runs its own dedicated FreeRTOS task** for these
  requests, plain ESP-IDF `esp_http_client` -- not ESPHome's `http_request`
  component or any fork of it (this project isn't ESPHome at all). The
  point is the same one the old ESPHome sidecar needed a third-party fork
  for: an occasional 20-40s Google stall blocks only that task, never
  sensor sampling or the REST/WS servers.

## Copy code with the device's existing secret

Run `make gsheets-code` in the firmware directory (or
`make -C flue-monitor gsheets-code` from the repository root).
It prompts for the dashboard password with hidden input, signs in, reads the
Sheets secret, and prints the ready-to-paste script and copies it with macOS
`pbcopy`. Override discovery with `HOST=192.168.1.137` when needed. Use the
monitor's LAN address; the tunnel's settings endpoint redacts credentials.
Password and session cookie stay in memory; the temporary session is logged
out after reading settings. No secret files are written. The printed code
and clipboard do contain the Sheets secret, as before. Authentication failures
stop without replacing the clipboard. This requires an interactive terminal
and Python 3; no extra Python packages are needed.

## Updating the deployed script

Editing `Code.gs` in the Apps Script editor doesn't take effect until you
redeploy: **Deploy -> Manage deployments -> pencil icon on the active
deployment -> Version: New version -> Deploy**. The web app URL stays the
same across versions.

## Room temperature

Each upload (temperature change, heartbeat and logged event) includes
`room_temperature` from the selected Bosch zone. The script appends it in
**Room Temperature (C)** (column G in the original layout), without moving the existing six columns.
Existing rows stay unchanged. Missing, failed or older-than-three-minute
readings are sent empty; old firmware also produces an empty cell. Valid zero
is retained and invalid values such as 1000 are rejected. For queued events,
the room measurement is captured at the tap, alongside the flue reading.

To enable the new column on the live sheet, copy the updated `Code.gs` into
the existing Apps Script project **while preserving its real SHARED_SECRET**,
then update the existing deployment to a new version as described above.
The webhook URL can stay the same. Updating only the firmware sends the extra
parameter but the old deployed script will ignore it.

Verification: `node tools/test_sheets_room.js` from the firmware project folder
runs the actual handler with a mock Sheet; it makes no requests to Google.
