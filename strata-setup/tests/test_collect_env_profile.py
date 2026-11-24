"""Unit tests for scripts/collect_env_profile.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import collect_env_profile as cep  # noqa: E402


class TestCollectEnvProfile(unittest.TestCase):
    def test_parse_lspci_vga(self):
        out = "00:02.0 VGA compatible controller: Intel\n01:00.0 3D controller: NVIDIA\n02:00.0 USB controller: x"
        devs = cep.parse_lspci_vga(out)
        self.assertEqual(len(devs), 2)

    def test_collect_profile_structure(self):
        profile = cep.collect_profile()
        self.assertIn("platform", profile)
        self.assertIn("python", profile)
        self.assertIn("cpu_count", profile)
        self.assertIn("gpus", profile)

    def test_cli_runs(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "profile.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "collect_env_profile.py"),
                 "--output", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text())
            self.assertIn("platform", data)


if __name__ == "__main__":
    unittest.main()
