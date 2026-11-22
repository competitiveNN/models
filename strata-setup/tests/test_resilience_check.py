import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import resilience_check as rc  # noqa: E402


class TestResilienceCheck(unittest.TestCase):
    def test_vram_resilience(self):
        res = rc.check_vram_resilience()
        self.assertIn("viable", res)

    def test_thermal_resilience(self):
        res = rc.check_thermal_resilience()
        self.assertTrue(res["viable"])

    def test_restart_recovery(self):
        res = rc.check_restart_recovery()
        self.assertTrue(res["viable"])


if __name__ == "__main__":
    unittest.main()