"""Unit tests for scripts/validate_warm_repeats.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_warm_repeats as vwr  # noqa: E402


class TestValidateWarmRepeatsFunctions(unittest.TestCase):
    def test_load_warm_files_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            d = vwr.load_warm_files(td)
            self.assertEqual(d, {})

    def test_validate_schema_missing_fields(self):
        errors = vwr.validate_schema({"tag": "t"}, Path("x"))
        self.assertTrue(any("missing fields" in e for e in errors))

    def test_validate_schema_ok(self):
        data = {
            "tag": "t", "repeats": 2, "per_run": [{"run": 1, "decode": 1.0, "prefill": 2.0}],
            "decode_median": 1.0, "prefill_median": 2.0, "decode_mean": 1.0,
            "prefill_mean": 2.0, "decode_stdev": 0.0, "prefill_stdev": 0.0,
        }
        errors = vwr.validate_schema(data, Path("x"))
        self.assertEqual(errors, [])

    def test_validate_medians_positive(self):
        data = {"decode_median": 0, "prefill_median": 5}
        errors = vwr.validate_medians_positive(data, Path("x"))
        self.assertTrue(any("decode_median not positive" in e for e in errors))
        data2 = {"decode_median": 1, "prefill_median": 5}
        self.assertEqual(vwr.validate_medians_positive(data2, Path("x")), [])

    def test_cli_runs_success(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_warm_repeats.py")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"CLI failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("validated successfully", result.stdout)

    def test_cli_json_out(self):
        out = ROOT / "runs" / "vw-test.json"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_warm_repeats.py"),
             "--json-out", str(out)],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0)
        self.assertTrue(out.exists())
        data = json.loads(out.read_text())
        self.assertTrue(data["passed"])
        self.assertGreater(data["count"], 0)
        out.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
