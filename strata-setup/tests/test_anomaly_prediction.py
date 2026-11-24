"""Unit tests for scripts/anomaly_prediction.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import anomaly_prediction as ap  # noqa: E402


class TestAnomalyPrediction(unittest.TestCase):
    def test_ewma_length(self):
        vals = [1.0, 2.0, 3.0]
        out = ap.ewma(vals)
        self.assertEqual(len(out), len(vals))

    def test_linear_fit_constant(self):
        slope, intercept = ap.linear_fit([5.0, 5.0, 5.0])
        self.assertEqual(slope, 0.0)
        self.assertEqual(intercept, 5.0)

    def test_predict_next_increasing(self):
        pred = ap.predict_next([1.0, 2.0, 3.0])
        self.assertGreater(pred, 3.0)

    def test_prediction_interval(self):
        lo, hi = ap.prediction_interval([1.0, 2.5, 2.8, 4.2])
        self.assertLess(lo, hi)

    def test_detect_predicted_regression_no_breach(self):
        history = [{"winner_decode": 12.0, "winner_prefill": 30.0} for _ in range(5)]
        res = ap.detect_predicted_regression(history, 10.0, 20.0)
        self.assertFalse(res["predicted_regression"])

    def test_detect_predicted_regression_breach(self):
        history = [{"winner_decode": 5.0, "winner_prefill": 10.0} for _ in range(5)]
        res = ap.detect_predicted_regression(history, 11.9, 22.9)
        self.assertTrue(res["predicted_regression"])

    def test_cli_runs(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            hp.write_text("".join(json.dumps({"winner_decode": 12.0, "winner_prefill": 30.0}) + "\n" for _ in range(5)))
            out = Path(td) / "pred.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "anomaly_prediction.py"),
                 "--history", str(hp), "--baseline-decode", "11.9",
                 "--baseline-prefill", "22.9", "--json-out", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text())
            self.assertIn("predicted_regression", data)


if __name__ == "__main__":
    unittest.main()
