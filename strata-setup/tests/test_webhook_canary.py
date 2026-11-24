"""Unit tests for scripts/webhook_canary.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import webhook_canary as wc  # noqa: E402


class TestWebhookCanary(unittest.TestCase):
    def test_dispatch_primary(self):
        router = wc.CanaryRouter("http://primary", "http://canary", canary_ratio=0.0)
        res = router.dispatch({"text": "x"}, send_func=lambda *a, **k: (True, "ok"))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["used"], "primary")

    def test_canary_selected(self):
        class FixedRandom:
            def random(self):
                return 0.0  # always below ratio -> canary
        router = wc.CanaryRouter("http://primary", "http://canary", canary_ratio=0.5, rng=FixedRandom())
        res = router.dispatch({"text": "x"}, send_func=lambda *a, **k: (True, "ok"))
        self.assertEqual(res["used"], "canary")

    def test_fallback_on_primary_failure(self):
        router = wc.CanaryRouter("http://primary", "http://canary", fallback="http://fallback", canary_ratio=0.0)
        calls = []
        def fake_send(url, payload, **kwargs):
            calls.append(url)
            if url == "http://primary":
                return False, "primary down"
            return True, "fallback ok"
        res = router.dispatch({"text": "x"}, send_func=fake_send)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["used"], "fallback")
        self.assertIn("http://fallback", calls)

    def test_rollback_after_failures(self):
        router = wc.CanaryRouter("http://primary", "http://canary", canary_ratio=0.5,
                                min_samples=2, failure_threshold=0.5)
        # Force canary selection each time with a constant RNG
        class AlwaysCanary:
            def random(self):
                return 0.0
        router.rng = AlwaysCanary()
        for _ in range(2):
            router.dispatch({"text": "x"}, send_func=lambda *a, **k: (False, "canary down"))
        self.assertEqual(router.canary_ratio, 0.0)
        self.assertTrue(any(d["decision"] == "rollback" for d in router.decisions))

    def test_promote_after_successes(self):
        router = wc.CanaryRouter("http://primary", "http://canary", canary_ratio=0.5,
                                min_samples=2, success_threshold=0.9)
        class AlwaysCanary:
            def random(self):
                return 0.0
        router.rng = AlwaysCanary()
        for _ in range(2):
            router.dispatch({"text": "x"}, send_func=lambda *a, **k: (True, "ok"))
        self.assertEqual(router.canary_ratio, 1.0)
        self.assertTrue(any(d["decision"] == "promote" for d in router.decisions))

    def test_summary(self):
        router = wc.CanaryRouter("http://primary", "http://canary", canary_ratio=0.0)
        router.dispatch({"text": "x"}, send_func=lambda *a, **k: (True, "ok"))
        s = router.summary()
        self.assertIn("stats", s)
        self.assertEqual(s["stats"]["primary"]["success"], 1)

    def test_cli_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "webhook_canary.py"),
             "--primary", "https://example.com/p", "--canary", "https://example.com/c",
             "--payload", '{"text":"x"}', "--dry-run"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
