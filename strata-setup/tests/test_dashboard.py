import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import b580_dashboard as dash  # noqa: E402


class TestB580Dashboard(unittest.TestCase):
    def test_dashboard_generation(self):
        text = dash.generate_dashboard()
        self.assertIn("Strata 2x B580 TP2 Dashboard", text)


if __name__ == "__main__":
    unittest.main()
