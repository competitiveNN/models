"""Integration tests for webhook dispatch in scripts/regression_alert.py."""

import http.server
import json
import socketserver
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import regression_alert as ra  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    # Class-level control
    status_code = 200
    fail_first_n = 0
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).received.append(json.loads(body))
        if type(self).fail_first_n > 0:
            type(self).fail_first_n -= 1
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(type(self).status_code)
        self.end_headers()

    def log_message(self, *args):
        pass


class TestWebhookDispatchIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        _Handler.status_code = 200
        _Handler.fail_first_n = 0
        _Handler.received = []

    def url(self):
        return f"http://127.0.0.1:{self.port}/hook"

    def test_single_dispatch_success(self):
        ok, msg = ra.send_webhook(self.url(), {"text": "hi", "severity": "info"}, dry_run=False, timeout=5, retries=1)
        self.assertTrue(ok)
        self.assertEqual(len(_Handler.received), 1)
        self.assertEqual(_Handler.received[0]["text"], "hi")

    def test_retry_on_500_then_success(self):
        _Handler.fail_first_n = 1
        ok, msg = ra.send_webhook(self.url(), {"text": "retry", "severity": "info"}, dry_run=False, timeout=5, retries=3)
        self.assertTrue(ok)
        # 2 requests total (one fail, one success)
        self.assertEqual(len(_Handler.received), 2)

    def test_retry_exhausted(self):
        _Handler.fail_first_n = 10
        ok, msg = ra.send_webhook(self.url(), {"text": "fail", "severity": "info"}, dry_run=False, timeout=5, retries=2)
        self.assertFalse(ok)
        self.assertIn("failed after", msg)

    def test_multi_target_dispatch(self):
        targets = [
            {"url": self.url(), "min_severity": "info"},
        ]
        payload = {"text": "multi", "severity": "warning"}
        results = ra.send_webhooks(targets, payload, dry_run=False, timeout=5, retries=1)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0][1])
        self.assertEqual(len(_Handler.received), 1)

    def test_multi_target_severity_skip(self):
        targets = [{"url": self.url(), "min_severity": "critical"}]
        payload = {"text": "skip", "severity": "info"}
        results = ra.send_webhooks(targets, payload, dry_run=False, timeout=5, retries=1)
        self.assertTrue(results[0][1])
        self.assertIn("skipped", results[0][2])
        self.assertEqual(len(_Handler.received), 0)


if __name__ == "__main__":
    unittest.main()
