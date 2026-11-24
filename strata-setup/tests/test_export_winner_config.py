"""Unit tests for scripts/export_winner_config.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestExportWinnerConfig(unittest.TestCase):
    def test_cli_runs(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "winner.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "export_winner_config.py"),
                 "--output", str(out)],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_text())
            self.assertEqual(data["winner_tag"], "r3-spec4-ec8192-pw2-ppr4-pool20-int8")
            self.assertIn("shell_defaults", data)
            self.assertIn("winner_throughput", data)

    def test_stdout_output(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "export_winner_config.py")],
            capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["winner_tag"], "r3-spec4-ec8192-pw2-ppr4-pool20-int8")


if __name__ == "__main__":
    unittest.main()
