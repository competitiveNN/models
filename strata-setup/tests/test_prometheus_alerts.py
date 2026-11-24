"""Unit tests for prometheus/strata-b580-alerts.yml."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestPrometheusAlerts(unittest.TestCase):
    def test_alerts_file_contains_regression_rules(self):
        p = ROOT / "prometheus" / "strata-b580-alerts.yml"
        self.assertTrue(p.exists())
        text = p.read_text()
        self.assertIn("StrataPerformanceRegression", text)
        self.assertIn("StrataPerformanceDrift", text)
        self.assertIn("strata_regression_alert", text)
        self.assertIn("strata_performance_drift", text)

    def test_alerts_file_valid_yaml_if_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        p = ROOT / "prometheus" / "strata-b580-alerts.yml"
        data = yaml.safe_load(p.read_text())
        self.assertIn("groups", data)
        self.assertGreater(len(data["groups"]), 0)


if __name__ == "__main__":
    unittest.main()
