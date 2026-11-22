import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import b580_thermal as thermal  # noqa: E402


class TestB580Thermal(unittest.TestCase):
    def test_thermal_data_structure(self):
        data = thermal.read_thermal_data()
        self.assertIn("gpus", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["gpus"], list)

    def test_prometheus_generation(self):
        # Test with mock data
        mock_data = {
            "gpus": [{"hwmon": "hwmon0", "temp_GPU": 65.0, "power_PKG": 85.5}],
            "count": 1
        }
        output = thermal.generate_prometheus_thermal(mock_data)
        self.assertIn("strata_gpu_temperature_celsius", output)
        self.assertIn("65.0", output)
        self.assertIn("strata_gpu_power_watts", output)
        self.assertIn("85.5", output)


if __name__ == "__main__":
    unittest.main()