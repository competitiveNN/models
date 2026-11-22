import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import b580_prometheus  # noqa: E402


class TestB580Prometheus(unittest.TestCase):
    def test_metrics_output(self):
        output = b580_prometheus.generate_prometheus_metrics()
        self.assertIn("strata_b580_device_present", output)
        self.assertIn("strata_level_zero_available", output)


if __name__ == "__main__":
    unittest.main()
