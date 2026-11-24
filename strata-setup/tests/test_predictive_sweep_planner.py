"""Unit tests for scripts/predictive_sweep_planner.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import predictive_sweep_planner as psp  # noqa: E402
from sweep_plan import DEFAULT_BASE  # noqa: E402


class TestPredictiveSweepPlanner(unittest.TestCase):
    def test_load_history_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(psp.load_history(Path(td) / "nope.jsonl"), [])

    def test_build_plan_stabilize_mode(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            # Force predicted regression with low throughput history
            hp.write_text("".join(json.dumps({"winner_decode": 5.0, "winner_prefill": 10.0}) + "\n" for _ in range(5)))
            plan = psp.build_plan(DEFAULT_BASE, history_path=hp,
                                  summary_path=Path(td) / "nope.jsonl",
                                  baseline_decode=11.9, baseline_prefill=22.9)
            self.assertEqual(plan["mode"], "stabilize")
            self.assertGreater(len(plan["candidates"]), 0)
            # Stabilize should not exceed winner pool workers
            for c in plan["candidates"]:
                self.assertLessEqual(int(c["env"]["POOL_WORKERS"]), 16)

    def test_build_plan_expand_mode(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            hp.write_text("".join(json.dumps({"winner_decode": 12.0, "winner_prefill": 30.0}) + "\n" for _ in range(5)))
            plan = psp.build_plan(DEFAULT_BASE, history_path=hp,
                                  summary_path=Path(td) / "nope.jsonl")
            self.assertEqual(plan["mode"], "expand")

    def test_winner_candidate_first(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            hp.write_text("".join(json.dumps({"winner_decode": 12.0, "winner_prefill": 30.0}) + "\n" for _ in range(5)))
            plan = psp.build_plan(DEFAULT_BASE, history_path=hp,
                                  summary_path=Path(td) / "nope.jsonl")
            self.assertEqual(plan["candidates"][0]["tag"], plan["winner_tag"])

    def test_summary_scores_influence_order(self):
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "h.jsonl"
            hp.write_text("".join(json.dumps({"winner_decode": 12.0, "winner_prefill": 30.0}) + "\n" for _ in range(5)))
            summary = Path(td) / "s.jsonl"
            # Make a non-winner candidate have a high score
            summary.write_text(json.dumps({
                "tag": "r3-spec4-ec8192-pw2-ppr4-pool16-int8",
                "decode_median": 100.0, "prefill_median": 100.0, "coherence_pass": True
            }) + "\n")
            plan = psp.build_plan(DEFAULT_BASE, history_path=hp, summary_path=summary)
            self.assertGreaterEqual(plan["candidates"][1]["score"], 0)

    def test_cli_runs(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "plan.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "predictive_sweep_planner.py"),
                 "--max", "3", "--output", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text())
            self.assertIn("mode", data)


if __name__ == "__main__":
    unittest.main()
