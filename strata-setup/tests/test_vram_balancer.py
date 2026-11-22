import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vram_balancer  # noqa: E402


class TestVramBalancer(unittest.TestCase):
    def test_estimation(self):
        res = vram_balancer.estimate_vram_allocation(65536, 8, 2, 12.0)
        self.assertIn("fits", res)
        self.assertIn("per_gpu_gb", res)
        self.assertTrue(res["fits"])


if __name__ == "__main__":
    unittest.main()
