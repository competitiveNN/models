"""Unit tests for scripts/webhook_failover.py."""

import http.server
import json
import socketserver
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import webhook_failover as wf  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_POST(self):
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *args):
        pass


class TestWebhookFailover(unittest.TestCase):
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

    def url(self):
        return f"http://127.0.0.1:{self.port}/hook"

    def setUp(self):
        _Handler.status = 200

    def test_primary_success(self):
        router = wf.FailoverRouter([self.url()], [])
        res = router.dispatch({"text": "hi"}, dry_run=False, timeout=5, retries=1)
        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["failover"])
        self.assertEqual(res["role"], "primary")

    def test_failover_to_backup(self):
        _Handler.status = 500
        backup_port = self.port  # same server becomes healthy after status reset
        # Use a second router with primary failing and backup same endpoint but status 200 not possible simultaneously.
        # Instead test event recording by forcing primary failure via unavailable endpoint.
        router = wf.FailoverRouter(["http://127.0.0.1:1/nope"], [self.url()])
        _Handler.status = 200
        res = router.dispatch({"text": "hi"}, dry_run=False, timeout=2, retries=1)
        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["failover"])
        self.assertEqual(res["role"], "backup")

    def test_all_fail(self):
        router = wf.FailoverRouter(["http://127.0.0.1:1/nope"], ["http://127.0.0.1:2/nope"])
        res = router.dispatch({"text": "hi"}, dry_run=False, timeout=1, retries=1)
        self.assertEqual(res["status"], "failed")

    def test_dry_run(self):
        router = wf.FailoverRouter([self.url()], [])
        res = router.dispatch({"text": "hi"}, dry_run=True, timeout=5, retries=1)
        self.assertEqual(res["status"], "ok")

    def test_health_summary(self):
        router = wf.FailoverRouter([self.url()], [])
        s = router.health_summary()
        self.assertIn("primary", s)
        self.assertIn("backup", s)

    def test_endpoint_availability_cooldown(self):
        ep = wf.Endpoint("http://x", cooldown=10)
        ep.mark_failure(now=100.0)
        self.assertFalse(ep.is_available(now=105.0))
        self.assertTrue(ep.is_available(now=111.0))

    def test_cli_dry_run(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "webhook_failover.py"),
             "--primary", self.url(), "--backup", self.url(),
             "--payload", '{"text":"x"}', "--dry-run"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
