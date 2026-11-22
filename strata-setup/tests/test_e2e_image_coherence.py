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
        self.assertTrue(hasattr(smoke, "get_running_digest"))
        self.assertTrue(hasattr(smoke, "verify_digest"))

    def test_run_cmd_function(self):
        rc, out, err = smoke.run_cmd(["echo", "hello"], timeout=10)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "hello")

    def test_launch_cmd_contains_gpu_config(self):
        self.assertIn("--gpu 0,1", smoke.LAUNCH_CMD)

    def test_launch_cmd_contains_model_config(self):
        self.assertIn("--family swift", smoke.LAUNCH_CMD)
        self.assertIn("--model IQ3_XXS", smoke.LAUNCH_CMD)
        self.assertIn("--model-path /model/", smoke.LAUNCH_CMD)

    def test_launch_cmd_contains_tuning(self):
        self.assertIn("pipeline-windows=2", smoke.LAUNCH_CMD)
        self.assertIn("vram-reserve-mib=256", smoke.LAUNCH_CMD)
        self.assertIn("expert-cache-per-layer", smoke.LAUNCH_CMD)
        self.assertIn("stream-experts", smoke.LAUNCH_CMD)
        self.assertIn("mmap-experts", smoke.LAUNCH_CMD)

    def test_constants(self):
        self.assertEqual(smoke.CONTAINER_NAME, "strata-e2e-smoke")
        self.assertEqual(smoke.CONTAINER_PORT, "8080")
        self.assertTrue(smoke.HEALTH_URL.endswith("/health"))
        self.assertTrue(smoke.COHERENCE_URL.endswith("/v1/chat/completions"))

    def test_main_callable(self):
        self.assertTrue(callable(smoke.main))


if __name__ == "__main__":
    unittest.main()
