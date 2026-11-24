"""Unit tests for scripts/performance_trend_report.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import performance_trend_report as ptr  # noqa: E402


class TestPerformanceTrendReport(unittest.TestCase):
    def test_sparkline_empty(self):
        self.assertEqual(ptr.sparkline([]), "")

    def test_sparkline_flat(self):
        s = ptr.sparkline([5.0, 5.0, 5.0])
        self.assertEqual(len(s), 3)
        self.assertTrue(all(c == ptr.SPARK_CHARS[0] for c in s))

    def test_sparkline_increasing(self):
        s = ptr.sparkline([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(len(s), 4)
        # last char should be highest
        self.assertEqual(s[-1], ptr.SPARK_CHARS[-1])

    def test_load_history_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(ptr.load_history(Path(td) / "nope.jsonl"), [])

    def test_load_history_parses(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"winner_decode": 10.0}) + "\n")
            path = Path(f.name)
        try:
            recs = ptr.load_history(path)
            self.assertEqual(len(recs), 1)
        finally:
            path.unlink(missing_ok=True)

    def test_generate_report_empty(self):
        with tempfile.TemporaryDirectory() as td:
            report = ptr.generate_report(Path(td) / "nope.jsonl")
            self.assertIn("No history available", report)

    def test_generate_report_with_data(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            recs = [
                {"timestamp": "t1", "winner_decode": 10.0, "winner_prefill": 25.0,
                 "baseline_decode": 9.0, "baseline_prefill": 20.0,
                 "decode_ratio": 1.1, "prefill_ratio": 1.25, "alert": False,
                 "drift_detected": False},
                {"timestamp": "t2", "winner_decode": 11.0, "winner_prefill": 26.0,
                 "baseline_decode": 9.0, "baseline_prefill": 20.0,
                 "decode_ratio": 1.2, "prefill_ratio": 1.3, "alert": False,
                 "drift_detected": False},
            ]
            hp.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
            report = ptr.generate_report(hp)
            self.assertIn("Performance Trend Report", report)
            self.assertIn("t2", report)

    def test_cli_runs(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            hp.write_text(json.dumps({"timestamp": "t1", "winner_decode": 10.0,
                                      "winner_prefill": 25.0, "baseline_decode": 9.0,
                                      "baseline_prefill": 20.0, "decode_ratio": 1.1,
                                      "prefill_ratio": 1.25, "alert": False,
                                      "drift_detected": False}) + "\n")
            out = Path(td) / "report.md"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "performance_trend_report.py"),
                 "--history", str(hp), "--out", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists())
            self.assertIn("Performance Trend Report", out.read_text())


if __name__ == "__main__":
    unittest.main()


class TestDetectAnomaly(unittest.TestCase):
    def test_detect_anomaly_insufficient_data(self):
        is_anom, z, mean, std = ptr.detect_anomaly([1.0, 2.0, 3.0])
        self.assertFalse(is_anom)
        self.assertEqual(z, 0.0)

    def test_detect_anomaly_flags_outlier(self):
        vals = [10.0] * 10 + [100.0]
        is_anom, z, mean, std = ptr.detect_anomaly(vals)
        self.assertTrue(is_anom)
        self.assertGreater(z, 2.5)

    def test_detect_anomaly_no_outlier(self):
        vals = [10.0, 10.2, 9.8, 10.1, 10.3, 9.9, 10.0, 10.2, 9.8, 10.1, 10.0]
        is_anom, z, mean, std = ptr.detect_anomaly(vals)
        self.assertFalse(is_anom)
