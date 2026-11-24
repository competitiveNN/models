"""Unit tests for scripts/sweep_plan.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sweep_plan as sp  # noqa: E402


class TestSweepPlan(unittest.TestCase):
    def test_generate_combinations_count(self):
        base = {"SPEC": "4", "KV": "int8"}
        knobs = {"SPEC": ["4", "5"], "KV": ["int8"]}
        combos = sp.generate_combinations(base, knobs)
        self.assertEqual(len(combos), 2)
        tags = {c["tag"] for c in combos}
        self.assertEqual(len(tags), 2)

    def test_generate_combinations_dedup(self):
        base = {"SPEC": "4", "KV": "int8"}
        knobs = {"SPEC": ["4"], "KV": ["int8"]}
        combos = sp.generate_combinations(base, knobs)
        self.assertEqual(len(combos), 1)

    def test_env_contains_base(self):
        base = {"SPEC": "4", "EXPERT_CACHE": "8192"}
        knobs = {"SPEC": ["4"]}
        combos = sp.generate_combinations(base, knobs)
        self.assertEqual(combos[0]["env"]["EXPERT_CACHE"], "8192")

    def test_cli_runs(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "plan.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "sweep_plan.py"),
                 "--max", "3", "--output", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text())
            self.assertEqual(len(data), 3)

    def test_cli_custom_knobs(self):
        with tempfile.TemporaryDirectory() as td:
            knobs = Path(td) / "knobs.json"
            knobs.write_text(json.dumps({"SPEC": ["3"]}))
            out = Path(td) / "plan.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "sweep_plan.py"),
                 "--knobs", str(knobs), "--output", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
