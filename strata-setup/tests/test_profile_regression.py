import unittest
import importlib.util
from pathlib import Path

script_path = Path(__file__).resolve().parents[1] / "scripts" / "profile_regression.py"
spec = importlib.util.spec_from_file_location("profile_regression", script_path)
prof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prof)

class TestProfileRegression(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue(script_path.exists())

if __name__ == "__main__":
    unittest.main()
