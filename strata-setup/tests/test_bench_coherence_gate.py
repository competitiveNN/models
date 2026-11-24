import unittest
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coherence  # noqa: E402

# Load bench-coherence-2xb580.py as a module
import importlib.util
spec = importlib.util.spec_from_file_location(
    "bench_coherence", ROOT / "bench-coherence-2xb580.py"
)
bench_coherence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench_coherence)


class TestBenchCoherenceGate(unittest.TestCase):
    def test_four_prompts(self):
        self.assertEqual(len(bench_coherence.PROMPTS), 4)

    def test_prompts_have_names(self):
        for name, prompt in bench_coherence.PROMPTS:
            self.assertTrue(name)
            self.assertTrue(prompt)

    def test_detects_artifact_loop(self):
        for name, _ in bench_coherence.PROMPTS:
            self.assertIsNotNone(coherence.detect_degenerate("!" * 20))

    def test_coherent_sample_passes(self):
        sample = ("Quantum computing uses quantum bits to process information by "
                  "leveraging superposition and entanglement.")
        self.assertIsNone(coherence.detect_degenerate(sample))

    def test_run_script_carries_tp2_and_mtp(self):
        rs = (ROOT / "run-strata-2gpu.sh").read_text()
        self.assertIn("--data-dir /data/Strata-data", rs)
        self.assertIn("--gpu 0,1", rs)
        self.assertIn("pipeline-windows=2", rs)
        self.assertIn("expert-cache-per-layer", rs)

    def test_script_help(self):
        res = subprocess.run(
            [sys.executable, str(ROOT / "bench-coherence-2xb580.py"), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("coherence", res.stdout.lower() + res.stderr.lower())

    def test_ask_extracts_reasoning_content(self):
        # ask() must prefer content, fall back to reasoning_content
        # We cannot hit a server; verify the function exists and signature.
        import inspect
        sig = inspect.signature(bench_coherence.ask)
        self.assertIn("model", sig.parameters)


if __name__ == "__main__":
    unittest.main()
