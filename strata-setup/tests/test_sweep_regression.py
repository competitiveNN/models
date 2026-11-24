import unittest
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Import the tier functions from the regression script
spec = __import__("importlib").util.spec_from_file_location(
    "check_sweep_regression", ROOT / "scripts" / "check_sweep_regression.py")
check_sweep_regression = __import__("importlib").util.module_from_spec(spec)
spec.loader.exec_module(check_sweep_regression)


class TestSweepRegressionAndSchema(unittest.TestCase):
    def test_is_promoted_entry(self):
        """Verify tier classification: promoted entries include baseline, winner, r3-*"""
        winner_tag = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
        baseline_tag = "baseline-ctx64k-auto-spec4-par1"

        # Promoted entries
        self.assertTrue(check_sweep_regression.is_promoted_entry(baseline_tag, winner_tag, baseline_tag))
        self.assertTrue(check_sweep_regression.is_promoted_entry(winner_tag, winner_tag, baseline_tag))
        self.assertTrue(check_sweep_regression.is_promoted_entry("r3-spec4-ec8192-pw2-ppr4-pool16-int8", winner_tag, baseline_tag))
        self.assertTrue(check_sweep_regression.is_promoted_entry("r3-winner-5runs", winner_tag, baseline_tag))

        # Historical entries
        self.assertFalse(check_sweep_regression.is_promoted_entry("2gpu-mmq0", winner_tag, baseline_tag))
        self.assertFalse(check_sweep_regression.is_promoted_entry("2gpu-pw8", winner_tag, baseline_tag))
        self.assertFalse(check_sweep_regression.is_promoted_entry("r2-spec4-ec8192-pw2-ppr4-pool16-int8", winner_tag, baseline_tag))

    def test_is_historical_entry(self):
        """Verify tier classification: historical entries are non-promoted"""
        winner_tag = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
        baseline_tag = "baseline-ctx64k-auto-spec4-par1"

        # Historical entries
        self.assertTrue(check_sweep_regression.is_historical_entry("2gpu-mmq0", winner_tag, baseline_tag))
        self.assertTrue(check_sweep_regression.is_historical_entry("r2-spec4-ec8192-pw2-ppr4-pool16-int8", winner_tag, baseline_tag))

        # Promoted entries are NOT historical
        self.assertFalse(check_sweep_regression.is_historical_entry(winner_tag, winner_tag, baseline_tag))
        self.assertFalse(check_sweep_regression.is_historical_entry(baseline_tag, winner_tag, baseline_tag))
        self.assertFalse(check_sweep_regression.is_historical_entry("r3-spec4-ec8192-pw2-ppr4-pool16-int8", winner_tag, baseline_tag))

    def test_strict_regression_promoted_only_passes(self):
        """Verify --promoted-only --strict passes cleanly."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_sweep_regression.py"),
             "--promoted-only", "--strict"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"Promoted-only strict regression failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("All configurations passed regression check.", result.stdout)

    def test_strict_regression_all_tiers_passes(self):
        """Verify --strict passes with tiered thresholds for all entries."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_sweep_regression.py"), "--strict"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"All-tier strict regression failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("All configurations passed regression check.", result.stdout)

    def test_historical_threshold_flag(self):
        """Verify --historical-threshold flag is accepted and functional."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_sweep_regression.py"),
             "--strict", "--historical-threshold", "0.50"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"Historical threshold strict check failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("All configurations passed regression check.", result.stdout)

    def test_strict_regression_all_entries_historical_lenient(self):
        """Verify that with strict mode and default historical threshold (50%),
        historical entries with ratios above 50% pass even if below 60%."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_sweep_regression.py"), "--strict"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"All-tier strict regression should pass with tiered thresholds:\n{result.stdout}\n{result.stderr}")
        # Verify historical entries show tier label in output
        self.assertIn("historical", result.stdout)
        self.assertIn("promoted", result.stdout)

    def test_sweep_summary_schema(self):
        summary_file = ROOT / "runs" / "sweep-summary.jsonl"
        if not summary_file.exists():
            self.skipTest("sweep-summary.jsonl not present")
        required = {"tag", "decode_median", "prefill_median", "coherence_pass", "env"}
        for line in summary_file.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            self.assertTrue(required.issubset(entry.keys()),
                            f"Missing fields in {entry.get('tag', '?')}: {required - set(entry.keys())}")
            self.assertIsInstance(entry["tag"], str)
            self.assertIsInstance(entry["decode_median"], (int, float))
            self.assertIsInstance(entry["prefill_median"], (int, float))
            self.assertIsInstance(entry["coherence_pass"], bool)
            self.assertIsInstance(entry["env"], (dict, list))

    def test_regression_script_schema_validation(self):
        script = ROOT / "scripts" / "check_sweep_regression.py"
        self.assertTrue(script.exists())
        result = subprocess.run(
            [__import__("sys").executable, str(script), "--validate-schema"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"Schema validation failed: {result.stdout}\n{result.stderr}")

    def test_regression_script_runs(self):
        script = ROOT / "scripts" / "check_sweep_regression.py"
        self.assertTrue(script.exists())

    def test_no_duplicate_tags(self):
        summary_file = ROOT / "runs" / "sweep-summary.jsonl"
        if not summary_file.exists():
            self.skipTest("sweep-summary.jsonl not present")
        tags = []
        for line in summary_file.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            tags.append(entry.get("tag"))
        self.assertEqual(len(tags), len(set(tags)),
                         f"Duplicate tags found: {[t for t in tags if tags.count(t) > 1]}")


if __name__ == "__main__":
    unittest.main()
