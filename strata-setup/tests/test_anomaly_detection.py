import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import anomaly_detection as ad  # noqa: E402


class TestAnomalyDetection(unittest.TestCase):
    def test_rolling_detector(self):
        detector = ad.RollingAnomalyDetector(window_size=20, z_threshold=2.5)
        
        # Add normal values
        for v in [10.0, 10.1, 9.9, 10.2, 9.8, 10.1, 10.0, 10.1, 9.9, 10.0]:
            result = detector.add_value("test", v)
            if result:
                self.assertFalse(result.is_anomaly)
        
        # Add anomalous value
        result = detector.add_value("test", 100.0)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_anomaly)
        self.assertEqual(result.severity, "warning")

    def test_iqr_anomalies(self):
        values = [10.0, 10.1, 9.9, 10.2, 9.8, 10.1, 10.0, 10.1, 9.9, 10.0, 50.0, -10.0]
        anomalies = ad.detect_iqr_anomalies(values)
        self.assertIn(50.0, anomalies)
        self.assertIn(-10.0, anomalies)
        self.assertNotIn(10.0, anomalies)


if __name__ == "__main__":
    unittest.main()