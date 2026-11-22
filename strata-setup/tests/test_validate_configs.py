import unittest, importlib.util
from pathlib import Path
script_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_configs.py"
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_configs", script_path)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
class TestValidateConfigs(unittest.TestCase):
    def test_check_config_bad_path(self):
        ok, errs = v.check_config(Path("/nonexistent/not_here.json"))
        self.assertFalse(ok)
        self.assertTrue(len(errs) > 0)
    def test_check_config_optimized_valid(self):
        ok, errs = v.check_config(ROOT / "configs" / "strata-swift-iq3_xxs-2gpu-optimized.json")
        self.assertTrue(ok)
        self.assertEqual(errs, [])
if __name__ == "__main__":
    unittest.main()
