import unittest
import sys
import tempfile
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark_trend as bt  # noqa: E402


class TestBenchmarkTrend(unittest.TestCase):
    def test_trend_tracker(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            tracker = bt.BenchmarkTrendTracker(temp_path)
            
            # Add two runs
            run1 = {"benchmarks": {"short_chat": {"results": {"throughput_median": 20.0}}}}
            run2 = {"benchmarks": {"short_chat": {"results": {"throughput_median": 15.0}}}}  # 25% drop
            
            tracker.add_run(run1)
            tracker.add_run(run2)
            
            # Check regression detection
            result = tracker.detect_regression("short_chat", threshold=0.15)
            self.assertEqual(result["status"], "regression")
            self.assertLess(result["ratio"], 0.85)
            
            # Test no regression
            run3 = {"benchmarks": {"short_chat": {"results": {"throughput_median": 19.5}}}}
            tracker.add_run(run3)
            result2 = tracker.detect_regression("short_chat", threshold=0.15)
            self.assertEqual(result2["status"], "ok")
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()