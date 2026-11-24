"""Unit tests for grafana/strata-regression-dashboard.json."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestGrafanaRegressionDashboard(unittest.TestCase):
    def test_dashboard_parses(self):
        p = ROOT / "grafana" / "strata-regression-dashboard.json"
        self.assertTrue(p.exists())
        data = json.loads(p.read_text())
        self.assertIn("dashboard", data)
        dash = data["dashboard"]
        self.assertEqual(dash["uid"], "strata-regression-perf")
        self.assertGreaterEqual(len(dash["panels"]), 8)
        # All panels reference strata_ metrics
        for panel in dash["panels"]:
            for t in panel.get("targets", []):
                self.assertTrue(t["expr"].startswith("strata_"), t["expr"])


if __name__ == "__main__":
    unittest.main()
