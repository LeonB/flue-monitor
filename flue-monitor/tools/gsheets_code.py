#!/usr/bin/env python3
"""Render the Apps Script using authenticated device settings, without secret files."""
import argparse
import getpass
import http.cookiejar
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def origin_for(host):
    url = host if '://' in host else 'http://' + host
    p = urllib.parse.urlsplit(url)
    if (p.scheme not in ('http', 'https') or not p.hostname or p.username or
            p.password or p.path not in ('', '/') or p.query or p.fragment):
        raise ValueError('HOST must be a hostname, IP address, or HTTP(S) origin.')
    return f'{p.scheme}://{p.netloc}'


def render(origin, password, template, opener):
    def request(path, body=None):
        req = urllib.request.Request(origin + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Origin': origin, 'Content-Type': 'application/json'})
        with opener.open(req, timeout=20) as response:
            return json.load(response)

    if request('/api/auth/login', {'password': password, 'remember': False}).get('success') is not True:
        raise ValueError('The monitor did not confirm sign-in.')
    try:
        settings = request('/api/settings')
        secret = settings.get('google_sheets_secret')
        if settings.get('credentials_redacted') or not isinstance(secret, str) or not secret:
            raise ValueError('No Sheets secret available. Check the monitor\'s Sheets settings and use its LAN address.')
        marker = json.dumps('REPLACE_ME_WITH_A_RANDOM_STRING')
        if template.count(marker) != 1:
            raise ValueError('Expected exactly one secret placeholder in Code.gs.')
        return template.replace(marker, json.dumps(secret, ensure_ascii=True))
    finally:
        try:
            request('/api/auth/logout', {})
        except (urllib.error.URLError, ValueError, OSError):
            print('Warning: could not close the temporary dashboard session.', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='flue-monitor.local')
    args = parser.parse_args()
    try:
        origin = origin_for(args.host)
        template = (Path(__file__).resolve().parents[1] / 'google-sheets-logger/Code.gs').read_text()
        # Refuse getpass's fallback to visible input if no terminal is available.
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass(f'Dashboard password ({origin}): ')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        code = render(origin, password, template, opener)
    except urllib.error.HTTPError as exc:
        message = {401: 'Incorrect dashboard password or expired session.',
                   429: 'Too many login attempts. Wait 30 seconds and retry.'}.get(exc.code, f'Monitor returned HTTP {exc.code}.')
        print('Error: ' + message, file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError, EOFError, getpass.GetPassWarning):
        print('Error: could not obtain script code. Check HOST, device availability, Sheets configuration and run from an interactive terminal.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        return 1
    sys.stdout.write(code)
    if shutil.which('pbcopy'):
        result = subprocess.run(['pbcopy'], input=code.encode(), stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            print('--- also copied to clipboard ---', file=sys.stderr)
        else:
            print('Warning: clipboard unavailable; script printed above.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
