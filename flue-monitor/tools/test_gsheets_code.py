"""Host checks: no real device, credentials or clipboard access."""
import io
import json
import unittest
import urllib.error
from gsheets_code import render, origin_for, NoRedirect


class FakeMonitor:
    def __init__(self, secret='quote" slash\\ newline\n & / $', reject=False, redacted=False):
        self.secret, self.reject, self.redacted = secret, reject, redacted
        self.paths = []

    def open(self, req, timeout):
        self.paths.append(req.selector)
        assert req.get_header('Origin') == 'http://monitor.local'
        assert timeout == 20
        if req.selector == '/api/auth/login':
            assert json.loads(req.data) == {'password': 'p"\\word', 'remember': False}
            if self.reject:
                raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, None)
            data = {'success': True}
        elif req.selector == '/api/settings':
            data = {'credentials_redacted': True} if self.redacted else {'google_sheets_secret': self.secret}
        else:
            assert req.selector == '/api/auth/logout'
            data = {'success': True}
        return io.StringIO(json.dumps(data))


class Tests(unittest.TestCase):
    def test_render_and_logout(self):
        monitor = FakeMonitor()
        result = render('http://monitor.local', 'p"\\word', 'const SECRET = "REPLACE_ME_WITH_A_RANDOM_STRING";', monitor)
        self.assertEqual(json.loads(result[len('const SECRET = '):-1]), monitor.secret)
        self.assertEqual(monitor.paths, ['/api/auth/login', '/api/settings', '/api/auth/logout'])

    def test_failed_auth_stops(self):
        monitor = FakeMonitor(reject=True)
        with self.assertRaises(urllib.error.HTTPError):
            render('http://monitor.local', 'p"\\word', '', monitor)
        self.assertEqual(monitor.paths, ['/api/auth/login'])

    def test_redacted_logs_out(self):
        monitor = FakeMonitor(redacted=True)
        with self.assertRaises(ValueError):
            render('http://monitor.local', 'p"\\word', '', monitor)
        self.assertEqual(monitor.paths[-1], '/api/auth/logout')

    def test_origins_and_redirects(self):
        self.assertEqual(origin_for('monitor.local'), 'http://monitor.local')
        self.assertEqual(origin_for('https://monitor.local/'), 'https://monitor.local')
        for host in ['http://user:password@host', 'ftp://host', 'http://host/path']:
            with self.assertRaises(ValueError): origin_for(host)
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere'))


if __name__ == '__main__': unittest.main()
