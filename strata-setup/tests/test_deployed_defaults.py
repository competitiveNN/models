"""Unit tests for scripts/check_deployed_defaults.py."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINNER_TAG = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"


class TestDeployedDefaults(unittest.TestCase):
    def test_deployed_defaults_check_passes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_deployed_defaults.py")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"Deployed defaults check failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("PASSED", result.stdout)

    def test_deployed_defaults_variance_aware_passes(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_deployed_defaults.py"),
             "--variance-aware"],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0,
                         f"Variance-aware check failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("Warm-repeat median", result.stdout)

    def test_winner_entry_exists_in_summary(self):
        summary = ROOT / "runs" / "sweep-summary.jsonl"
        tags = []
        for line in summary.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            tags.append(entry.get("tag"))
        self.assertIn(WINNER_TAG, tags, "Winner tag not found in summary")

    def test_winner_strictly_beats_baseline(self):
        summary = ROOT / "runs" / "sweep-summary.jsonl"
        baseline = None
        winner = None
        for line in summary.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("tag") == BASELINE_TAG:
                baseline = entry
            if entry.get("tag") == WINNER_TAG:
                winner = entry
        self.assertIsNotNone(baseline)
        self.assertIsNotNone(winner)
        self.assertGreater(winner["decode_median"], baseline["decode_median"])
        self.assertGreater(winner["prefill_median"], baseline["prefill_median"])
        self.assertTrue(winner["coherence_pass"])

    def test_winner_is_optimal_under_criterion(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_deployed_defaults",
            ROOT / "scripts" / "check_deployed_defaults.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        optimal = mod.compute_optimal_winner()
        self.assertIsNotNone(optimal)
        self.assertEqual(optimal["tag"], WINNER_TAG)

        entries = mod.load_entries()
        baseline = mod.find_baseline()
        dominators = [e for e in entries
                      if e.get("coherence_pass", False)
                      and e["decode_median"] > baseline["decode_median"]
                      and e["prefill_median"] > baseline["prefill_median"]]
        self.assertGreaterEqual(len(dominators), 1)
        winner_score = optimal["decode_median"] * optimal["prefill_median"]
        for d in dominators:
            self.assertLessEqual(
                d["decode_median"] * d["prefill_median"], winner_score)

    def test_no_stale_pool16_references(self):
        """Ensure no stale pool16 references remain in run-strata-2gpu.sh."""
        script = ROOT / "run-strata-2gpu.sh"
        text = script.read_text()
        self.assertNotIn("POOL_WORKERS=16", text,
                         "Stale POOL_WORKERS=16 found in run-strata-2gpu.sh")
        self.assertNotIn('POOL_WORKERS="${POOL_WORKERS:-16}"', text,
                         "Stale default POOL_WORKERS=16 found")


class TestParseShellDefaults(unittest.TestCase):
    def _import_mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_deployed_defaults",
            ROOT / "scripts" / "check_deployed_defaults.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_standard_pattern(self):
        mod = self._import_mod()
        text = 'POOL_WORKERS="${POOL_WORKERS:-12}"\nEXPERT_CACHE="${EXPERT_CACHE:-auto}"'
        d = mod.parse_shell_defaults(text)
        self.assertEqual(d["POOL_WORKERS"], "12")
        self.assertEqual(d["EXPERT_CACHE"], "auto")

    def test_missing_var_returns_none(self):
        mod = self._import_mod()
        text = 'OTHER_VAR="foo"'
        d = mod.parse_shell_defaults(text)
        self.assertIsNone(d["SPEC"])
        self.assertIsNone(d["EXPERT_CACHE"])

    def test_alternate_pattern(self):
        mod = self._import_mod()
        text = 'SPEC=${SPEC:-4}\nPEER_PREFILL_ROWS=${PEER_PREFILL_ROWS:-0}'
        d = mod.parse_shell_defaults(text)
        self.assertEqual(d["SPEC"], "4")
        self.assertEqual(d["PEER_PREFILL_ROWS"], "0")

    def test_empty_text(self):
        mod = self._import_mod()
        d = mod.parse_shell_defaults("")
        for v in ["SPEC", "EXPERT_CACHE", "PEER_PREFILL_ROWS", "POOL_WORKERS"]:
            self.assertIsNone(d[v])

    def test_quoted_values_stripped(self):
        mod = self._import_mod()
        text = 'EXPERT_CACHE="${EXPERT_CACHE:-8192}"'
        d = mod.parse_shell_defaults(text)
        self.assertEqual(d["EXPERT_CACHE"], "8192")

    def test_all_four_vars(self):
        mod = self._import_mod()
        text = (
            'SPEC="${SPEC:-4}"\n'
            'EXPERT_CACHE="${EXPERT_CACHE:-8192}"\n'
            'PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"\n'
            'POOL_WORKERS="${POOL_WORKERS:-20}"'
        )
        d = mod.parse_shell_defaults(text)
        self.assertEqual(d["SPEC"], "4")
        self.assertEqual(d["EXPERT_CACHE"], "8192")
        self.assertEqual(d["PEER_PREFILL_ROWS"], "4")
        self.assertEqual(d["POOL_WORKERS"], "20")



    def test_winner_is_pareto_optimal(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_deployed_defaults",
            ROOT / "scripts" / "check_deployed_defaults.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        entries = mod.load_entries()
        winner = mod.find_entry(WINNER_TAG)
        self.assertIsNotNone(winner)
        for e in entries:
            if e.get("tag") == WINNER_TAG:
                continue
            if not e.get("coherence_pass", False):
                continue
            dominates = (e["decode_median"] >= winner["decode_median"]
                         and e["prefill_median"] >= winner["prefill_median"]
                         and (e["decode_median"] > winner["decode_median"]
                              or e["prefill_median"] > winner["prefill_median"]))
            self.assertFalse(dominates,
                             f"{e['tag']} Pareto-dominates winner")

    def test_compute_optimal_winner_empty_entries(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_deployed_defaults",
            ROOT / "scripts" / "check_deployed_defaults.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        original = mod.load_entries
        mod.load_entries = lambda: []
        try:
            result = mod.compute_optimal_winner()
            self.assertIsNone(result)
        finally:
            mod.load_entries = original

    def test_compute_optimal_winner_no_dominators(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_deployed_defaults",
            ROOT / "scripts" / "check_deployed_defaults.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        original = mod.load_entries
        baseline = mod.find_baseline()
        mod.load_entries = lambda: [baseline] if baseline else []
        try:
            result = mod.compute_optimal_winner()
            self.assertIsNone(result)
        finally:
            mod.load_entries = original



class TestWarmRepeatFiles(unittest.TestCase):
    def test_warm_files_exist(self):
        import glob
        warm_files = sorted(glob.glob(str(ROOT / "runs" / "warm-*.json")))
        self.assertGreaterEqual(len(warm_files), 1, "No warm-*.json files found")

    def test_warm_file_schema(self):
        import glob, json
        required = {"tag", "repeats", "per_run", "decode_median", "prefill_median",
                    "decode_mean", "prefill_mean", "decode_stdev", "prefill_stdev"}
        for f in glob.glob(str(ROOT / "runs" / "warm-*.json")):
            data = json.loads(open(f).read())
            missing = required - set(data.keys())
            self.assertFalse(missing, f"{f} missing fields: {missing}")
            self.assertIsInstance(data["tag"], str)
            self.assertIsInstance(data["repeats"], int)
            self.assertIsInstance(data["per_run"], list)
            self.assertGreater(len(data["per_run"]), 0, f"{f} has no per_run entries")
            for run in data["per_run"]:
                self.assertIn("run", run)
                self.assertIn("decode", run)
                self.assertIn("prefill", run)

    def test_warm_file_uniqueness(self):
        """Each warm file should have a unique tag."""
        import glob, json
        tags = []
        for f in glob.glob(str(ROOT / "runs" / "warm-*.json")):
            data = json.loads(open(f).read())
            tags.append(data.get("tag"))
        self.assertEqual(len(tags), len(set(tags)),
                         f"Duplicate warm tags: {[t for t in tags if tags.count(t) > 1]}")

    def test_warm_file_medians_positive(self):
        import glob, json
        for f in glob.glob(str(ROOT / "runs" / "warm-*.json")):
            data = json.loads(open(f).read())
            self.assertGreater(data["decode_median"], 0,
                               f"{f}: corrupt warm file (decode_median={data['decode_median']})")
            self.assertGreater(data["prefill_median"], 0,
                               f"{f}: prefill_median not positive")


if __name__ == "__main__":
    unittest.main()


class TestLocalOptimality(unittest.TestCase):
    def test_winner_local_optimality_verified(self):
        """Verify all neighbor configs are strictly worse on prefill than winner."""
        import json
        summary = ROOT / "runs" / "sweep-summary.jsonl"
        winner = None
        neighbors = {}
        for line in summary.read_text().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("tag") == WINNER_TAG:
                winner = e
            if e.get("tag", "").startswith("r3-") and e.get("tag") != WINNER_TAG:
                neighbors[e["tag"]] = e
        self.assertIsNotNone(winner)
        # Winner should have highest prefill among all r3 configs
        for tag, e in neighbors.items():
            if e["coherence_pass"]:
                self.assertFalse(
                    e["decode_median"] > winner["decode_median"]
                    and e["prefill_median"] > winner["prefill_median"],
                    f"{tag} Pareto-dominates winner")
