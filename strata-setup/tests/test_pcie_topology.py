import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import b580_pcie_topology as probe  # noqa: E402


class TestB580PCIeTopology(unittest.TestCase):
    def test_probe_structure(self):
        data = probe.probe_pcie()
        self.assertIn("devices", data)
        self.assertIn("count", data)
        for dev in data["devices"]:
            self.assertIn("card", dev)


if __name__ == "__main__":
    unittest.main()
