import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import strata_soak_test as soak  # noqa: E402


class TestStrataSoakTest(unittest.TestCase):
    def test_soak_structure(self):
        res = soak.run_soak_test("http://localhost:1235", iterations=2)
        self.assertEqual(res["iterations"], 2)
        self.assertIn("results", res)
        self.assertEqual(len(res["results"]), 2)


if __name__ == "__main__":
    unittest.main()
