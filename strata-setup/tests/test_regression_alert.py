"""Unit tests for scripts/regression_alert.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import regression_alert as ra  # noqa: E402


class TestRegressionAlertFunctions(unittest.TestCase):
    def test_load_entries_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            entries = ra.load_entries(Path(td) / "nope.jsonl")
            self.assertEqual(entries, [])

    def test_load_entries_parses_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"tag": "a", "decode_median": 1.0}) + "\n")
            f.write("\n")
            f.write(json.dumps({"tag": "b", "decode_median": 2.0}) + "\n")
            path = Path(f.name)
        try:
            entries = ra.load_entries(path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["tag"], "a")
        finally:
            path.unlink(missing_ok=True)

    def test_find_entry(self):
        entries = [{"tag": "x"}, {"tag": "y"}]
        self.assertEqual(ra.find_entry(entries, "y")["tag"], "y")
        self.assertIsNone(ra.find_entry(entries, "z"))

    def test_load_warm_median_returns_data(self):
        wm = ra.load_warm_median("r3-spec4-ec8192-pw2-ppr4-pool20-int8")
        self.assertIsNotNone(wm)
        self.assertGreater(wm["decode_median"], 0)
        self.assertGreater(wm["prefill_median"], 0)

    def test_load_warm_median_missing_tag_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            wm = ra.load_warm_median("nope-tag", runs_dir=td)
            self.assertIsNone(wm)

    def test_build_report_structure(self):
        entries = ra.load_entries()
        report = ra.build_report(entries)
        self.assertIn("alert", report)
        self.assertFalse(report["alert"])
        self.assertIn("checks", report)
        for c in ("decode_beats_baseline", "prefill_beats_baseline", "winner_coherence"):
            self.assertIn(c, report["checks"])
            self.assertTrue(report["checks"][c]["passed"])

    def test_build_report_missing_baseline_alerts(self):
        entries = [e for e in ra.load_entries() if e.get("tag") != ra.BASELINE_TAG]
        report = ra.build_report(entries)
        self.assertTrue(report["alert"])
        self.assertFalse(report["checks"]["baseline_found"]["passed"])

    def test_detect_drift_insufficient_data(self):
        d = ra.detect_drift([], 12.0, 30.0)
        self.assertEqual(d["status"], "insufficient_data")
        self.assertFalse(d["drift_detected"])

    def test_detect_drift_detects_drop(self):
        history = [
            {"winner_decode": 12.0, "winner_prefill": 30.0},
            {"winner_decode": 12.0, "winner_prefill": 30.0},
            {"winner_decode": 12.0, "winner_prefill": 30.0},
        ]
        d = ra.detect_drift(history, 9.0, 30.0, threshold=0.10)
        self.assertTrue(d["drift_detected"])
        self.assertEqual(d["status"], "drift")

    def test_detect_drift_ok(self):
        history = [
            {"winner_decode": 12.0, "winner_prefill": 30.0},
            {"winner_decode": 12.0, "winner_prefill": 30.0},
        ]
        d = ra.detect_drift(history, 12.0, 30.0, threshold=0.10)
        self.assertFalse(d["drift_detected"])
        self.assertEqual(d["status"], "ok")

    def test_append_and_load_history(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "hist.jsonl"
            ra.append_history({"a": 1}, hp)
            ra.append_history({"a": 2}, hp)
            recs = ra.load_history(hp)
            self.assertEqual(len(recs), 2)
            self.assertEqual(recs[1]["a"], 2)

    def test_build_webhook_payload(self):
        report = ra.build_report(ra.load_entries())
        payload = ra.build_webhook_payload(report, None)
        self.assertIn("text", payload)
        self.assertFalse(payload["alert"])

    def test_send_webhook_dry_run(self):
        ok, msg = ra.send_webhook("http://example.com/hook", {"x": 1}, dry_run=True)
        self.assertTrue(ok)
        self.assertTrue(msg.startswith("dry-run:"))

    def test_critical_checks_constant(self):
        self.assertIn("decode_beats_baseline", ra.CRITICAL_CHECKS)


class TestRegressionAlertCLI(unittest.TestCase):
    def test_cli_runs_success(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "regression_alert.py"),
             "--no-history", "--json-out", str(ROOT / "runs" / "regression-alert.json")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"CLI failed:\n{result.stdout}\n{result.stderr}")
        # report file written
        self.assertTrue((ROOT / "runs" / "regression-alert.json").exists())

    def test_cli_dry_run_webhook(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "regression_alert.py"),
             "--no-history", "--dry-run", "--webhook-url", "http://example.com/hook",
             "--json-out", str(ROOT / "runs" / "regression-alert.json")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"CLI dry-run failed:\n{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()


class TestWebhookMultiTarget(unittest.TestCase):
    def test_parse_comma_separated(self):
        targets = ra.parse_webhook_targets("http://a.com,http://b.com")
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["url"], "http://a.com")

    def test_parse_json_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["http://x.com", {"url": "http://y.com", "min_severity": "warning"}], f)
            path = f.name
        try:
            targets = ra.parse_webhook_targets(path)
            self.assertEqual(len(targets), 2)
            self.assertEqual(targets[1]["min_severity"], "warning")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_parse_empty(self):
        self.assertEqual(ra.parse_webhook_targets(""), [])
        self.assertEqual(ra.parse_webhook_targets(None), [])

    def test_send_webhooks_severity_filter(self):
        targets = [{"url": "http://a.com", "min_severity": "critical"}]
        payload = {"severity": "info", "text": "hi"}
        results = ra.send_webhooks(targets, payload, dry_run=True)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0][1])  # skipped counts as ok
        self.assertIn("skipped", results[0][2])

    def test_severity_order(self):
        self.assertLess(ra.SEVERITY_ORDER["info"], ra.SEVERITY_ORDER["critical"])


class TestWebhookValidationAndDeadLetter(unittest.TestCase):
    def test_validate_webhook_targets_ok(self):
        targets = ra.parse_webhook_targets("https://example.com/hook")
        self.assertEqual(ra.validate_webhook_targets(targets), [])

    def test_validate_webhook_targets_bad_url(self):
        targets = [{"url": "not-a-url", "min_severity": "info"}]
        errors = ra.validate_webhook_targets(targets)
        self.assertTrue(errors)

    def test_validate_webhook_targets_bad_severity(self):
        targets = [{"url": "https://example.com/hook", "min_severity": "urgent"}]
        errors = ra.validate_webhook_targets(targets)
        self.assertTrue(errors)

    def test_cli_validate_webhooks_success(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "regression_alert.py"),
             "--validate-webhooks", "--webhook-targets",
             str(ROOT / "configs" / "webhook-targets.example.json")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_write_dead_letter(self):
        with tempfile.TemporaryDirectory() as td:
            dl = Path(td) / "dead.jsonl"
            ra.write_dead_letter([{"url": "x", "error": "boom"}], dl)
            self.assertTrue(dl.exists())
            lines = dl.read_text().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["error"], "boom")

    def test_trim_history(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            for i in range(5):
                ra.append_history({"i": i}, hp)
            ra.trim_history(hp, 3)
            recs = ra.load_history(hp)
            self.assertEqual(len(recs), 3)
            self.assertEqual(recs[0]["i"], 2)

    def test_backoff_jitter_runs(self):
        # ensure send_webhook retry path executes without error on failure
        ok, msg = ra.send_webhook("http://127.0.0.1:1/nope", {"x": 1}, dry_run=False, timeout=1, retries=1)
        self.assertFalse(ok)
