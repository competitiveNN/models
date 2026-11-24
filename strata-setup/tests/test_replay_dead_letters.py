"""Unit tests for scripts/replay_dead_letters.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import replay_dead_letters as rdl  # noqa: E402


class TestReplayDeadLetters(unittest.TestCase):
    def test_load_dead_letters_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(rdl.load_dead_letters(Path(td) / "nope.jsonl"), [])

    def test_load_dead_letters_parses(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"url": "http://x", "payload": {"a": 1}}) + "\n")
            path = Path(f.name)
        try:
            recs = rdl.load_dead_letters(path)
            self.assertEqual(len(recs), 1)
        finally:
            path.unlink(missing_ok=True)

    def test_cli_dry_run_replays(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.jsonl"
            out = Path(td) / "out.jsonl"
            inp.write_text(json.dumps({"url": "http://example.com/hook", "payload": {"text": "hi"}}) + "\n")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "replay_dead_letters.py"),
                 "--input", str(inp), "--output", str(out), "--dry-run"],
                capture_output=True, text=True, cwd=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stderr)
            # dry-run succeeds, so output should be empty
            self.assertTrue(out.exists())
            self.assertEqual(out.read_text(), "")


if __name__ == "__main__":
    unittest.main()
