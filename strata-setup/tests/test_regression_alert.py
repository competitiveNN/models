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
