#!/usr/bin/env python3
"""Provision via USB, then check only the standalone probe's public endpoints."""
import argparse
import asyncio
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

import serial
import websockets


def provision(port, settings):
    values = [settings["ssid"], settings["password"], settings["tunnel_token"]]
    limits = [32, 64, 4095]
    for value, limit in zip(values, limits):
        if not isinstance(value, str) or "\n" in value or "\r" in value or len(value.encode()) > limit:
            raise ValueError("Invalid credential field length or line ending")
    with serial.Serial(port=None, baudrate=115200, timeout=.2) as connection:
        connection.dtr = False
        connection.rts = False
        connection.port = port
        connection.open()
        expected = [b"PROBE_SSID", b"PROBE_PASSWORD", b"PROBE_TUNNEL_TOKEN"]
        index = 0
        deadline = time.monotonic() + 180
        buffer = b""
        while time.monotonic() < deadline:
            buffer += connection.read(1024)
            if index < len(expected) and expected[index] in buffer:
                connection.write(values[index].encode() + b"\n")
                index += 1
                buffer = b""
            elif b"PROBE_TUNNEL_STARTED" in buffer:
                print("Credentials supplied; tunnel task started (edge registration not yet confirmed).")
                return
            elif b"PROBE_TIME_FAILED" in buffer or b"INPUT_TOO_LONG" in buffer:
                raise RuntimeError("Device rejected provisioning or could not synchronize time")
            # Do not echo raw device output or credentials.
            buffer = buffer[-8192:]
        raise TimeoutError("Provisioning did not finish; check USB, Wi-Fi and device boot")


def request(base, path, body=None):
    req = urllib.request.Request(base + path, data=body,
                                 headers={"User-Agent": "FlueTunnelProbe/1.0"})
    if body is not None:
        req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.status, response.read()


async def check(base):
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
        raise ValueError("Use an HTTPS origin without a path")
    base = base.rstrip("/")
    # Cloudflare may need time to register the connector.
    last_error = None
    for _ in range(30):
        try:
            status, body = request(base, "/status")
            before = json.loads(body)
            assert before["probe"] == "cloudflare-s3"
            break
        except (urllib.error.URLError, ValueError, AssertionError) as exc:
            last_error = type(exc).__name__
            await asyncio.sleep(2)
    else:
        raise RuntimeError("Probe not reachable: " + str(last_error))
    for size in (0, 1, 128, 1024, 4096):
        payload = bytes(i % 251 for i in range(size))
        status, body = request(base, "/echo", payload)
        assert status == 200 and body == payload
    try:
        request(base, "/echo", b"x" * 4097)
        raise AssertionError("Oversized body was accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 413
    ws_url = urllib.parse.urlunsplit(("wss", parsed.netloc, "/ws", "", ""))
    async with websockets.connect(ws_url, open_timeout=20, max_size=4096,
                                  user_agent_header="FlueTunnelProbe/1.0") as websocket:
        for i in range(25):
            payload = f"probe-{i}"
            await websocket.send(payload)
            assert await asyncio.wait_for(websocket.recv(), 10) == payload
        payload = bytes(range(256)) * 4
        await websocket.send(payload)
        assert await asyncio.wait_for(websocket.recv(), 10) == payload
        await asyncio.wait_for(await websocket.ping(), 10)
    for _ in range(25):
        status, body = request(base, "/status")
        assert status == 200 and json.loads(body)["probe"] == "cloudflare-s3"
    await asyncio.sleep(3)
    _, body = request(base, "/status")
    after = json.loads(body)
    print(json.dumps({"http": "PASS", "body_sizes": [0, 1, 128, 1024, 4096],
                      "oversized_body": 413, "websocket_echo_messages": 26,
                      "websocket_ping": "PASS", "repeated_gets": 25,
                      "heap_before": before, "heap_after": after}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", help="Provision credentials to this already-flashed S3 first")
    args = parser.parse_args()
    settings = json.loads(args.config.read_text())
    if args.port:
        provision(args.port, settings)
    asyncio.run(check(settings["url"]))


if __name__ == "__main__":
    main()
