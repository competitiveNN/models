import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import e2e_image_coherence_smoke as smoke  # noqa: E402


class TestE2EImageCoherenceSmoke(unittest.TestCase):
    def test_script_structure(self):
        self.assertTrue(hasattr(smoke, "run_cmd"))
        self.assertTrue(hasattr(smoke, "start_container"))
        self.assertTrue(hasattr(smoke, "wait_for_health"))
        self.assertTrue(hasattr(smoke, "run_coherence_gate"))
        self.assertTrue(hasattr(smoke, "cleanup"))
        self.assertTrue(hasattr(smoke, "main"))


    def test_run_cmd_function(self):
        rc, out, err = smoke.run_cmd(["echo", "hello"], timeout=10)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "hello")

if __name__ == "__main__":
    unittest.main()