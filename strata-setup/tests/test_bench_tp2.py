import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark_trend as bt  # noqa: E402
import vram_balancer as vb  # noqa: E402


class TestBenchTP2Integration(unittest.TestCase):
    def test_benchmark_trend_tracker(self):
        tracker = bt.BenchmarkTrendTracker()
        self.assertTrue(hasattr(tracker, "add_run"))
        self.assertTrue(hasattr(tracker, "detect_regression"))
        self.assertTrue(hasattr(tracker, "generate_report"))

    def test_vram_balancer_fits(self):
        result = vb.estimate_vram_allocation(65536, 8, 2, 12.0)
        self.assertTrue(result["fits"])
        self.assertGreater(result["estimated_reserve_gb"], 0)


if __name__ == "__main__":
    unittest.main()