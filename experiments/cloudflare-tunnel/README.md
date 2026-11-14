# Standalone Cloudflare Tunnel probe

This experiment runs **on an ESP32-S3**, independently of flue-monitor.
It uses igrr/esp-cf-tunnel at the commit pinned in main/idf_component.yml.
It has no dependency on the PageKite client or the stove-monitor HTTP server.

Endpoints through a dedicated Cloudflare test hostname:

- GET /status: probe identity, uptime, internal free/minimum heap and largest block.
- POST /echo: exact binary body echo, limited to 4096 bytes.
- /ws: WebSocket text/binary echo and ping handling.
- Other paths: 404. No actuator, OTA, settings or network-proxy endpoints.

The prototype uses one edge connection and four concurrent streams, with a
4096-byte stream window. It starts without requiring PSRAM. This intentionally
tests the smaller internal-RAM budget before considering the monitor integration.
No performance, stability or live-edge claim follows from a successful build.

## Credentials and routing

Create a **separate remotely managed test tunnel** and route a test hostname to
HTTP localhost:80. Supply its **connector token**, not an account-wide API key.
This prototype handles requests directly in callbacks; it does not start a
localhost web server or proxy other LAN services.

Use a local JSON file outside git, for example credentials.json (ignored here):

    {
      "ssid": "YOUR_WIFI",
      "password": "YOUR_WIFI_PASSWORD",
      "tunnel_token": "YOUR_CONNECTOR_TOKEN",
      "url": "https://YOUR_TEST_HOSTNAME"
    }

The USB provisioning tool reads that file directly; never pass credentials on
the command line or paste them into a chat. The prototype reads SSID, password
and token over USB and does not print them or persist them to NVS. Provisioning
must be repeated after reboot. It waits for SNTP before verifying edge TLS.

## Build

Activate ESP-IDF 6.2 with the S3 toolchain and run:

    idf.py set-target esp32s3
    idf.py build

Generated dependencies.lock pins the library and HTTP/2 dependency.
sdkconfig.defaults targets the previously identified S3 rev0.2, 8MB flash,
USB Serial/JTAG console. Verify the chip again before flashing.

The build/flash workflow is intentionally separate from check.py. Back up the
new S3's flash before its first test flash. Do not run this experiment on the
display or the flue-monitor. Do not erase NVS automatically; initialization
errors stop the probe.

## Test after flashing

Install pyserial and websockets in a temporary host Python environment, then:

    python check.py --config /absolute/path/to/credentials.json --port /dev/cu.usbmodem...

The S3 must already be running this probe. The tool supplies credentials when
the USB prompts arrive, then verifies:
HTTP status/identity; binary echoes at five sizes; rejection of a 4097-byte
body; 25 text and one binary WebSocket echoes; ping/pong; 25 further HTTP GETs.
It reports before/after heap samples. A short run is not a leak or soak test.

The four-connection S3 run registered all four connections and Cloudflare reported
`healthy`. The initial HTTP/body-limit and WebSocket checks passed, but within
about 150 seconds free internal heap fell to about 36 kB (minimum about 28 kB).
The library then rejected a request with HTTP 503 and logged `low on memory`.
The previous one-connection run had about 201 kB free. The probe therefore uses
one connection again; four connections are not usable in this tested configuration
without PSRAM or further memory optimization.

With the device already provisioned, omit --port to rerun public checks.

## Remaining integration work

Passing this experiment would establish a native tunnel and WebSocket transport,
not a production PageKite replacement. Before replacing the monitor client,
validate streamed request/response forwarding, large uploads/OTA without a
second firmware image buffered in RAM, authentication/cookies, reconnect after
Wi-Fi loss, long-lived WebSockets, memory under concurrent TLS clients and a
long soak. Keep production routing unchanged until those checks pass.
