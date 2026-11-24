import unittest
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestSweepRegressionAndSchema(unittest.TestCase):
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
