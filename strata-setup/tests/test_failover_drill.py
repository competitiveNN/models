import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import failover_drill  # noqa: E402


class TestFailoverDrill(unittest.TestCase):
    def test_drill_recovery(self):
        res = failover_drill.run_failover_drill(2)
        self.assertIn("viable", res)
        self.assertTrue(res["viable"])


if __name__ == "__main__":
    unittest.main()
