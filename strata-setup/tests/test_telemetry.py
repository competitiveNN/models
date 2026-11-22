import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import b580_telemetry  # noqa: E402


TestTele = b580_telemetry


class TestB580Telemetry(unittest.TestCase):
    def test_probe_telemetry_structure(self):
        data = TestTele.probe_telemetry()
        self.assertIn("status", data)
        self.assertIn("sys_drm", data)
        self.assertIn("level_zero", data)


if __name__ == "__main__":
    unittest.main()
