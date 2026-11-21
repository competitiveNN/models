import unittest
import importlib.util
from pathlib import Path

script_path = Path(__file__).resolve().parents[1] / "scripts" / "summarize_coherence.py"
spec = importlib.util.spec_from_file_location("summarize_coherence", script_path)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

class TestSummarizeCoherence(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue(script_path.exists())

if __name__ == "__main__":
    unittest.main()
