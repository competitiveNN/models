import unittest
import sys
import tempfile
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import pin_image_digest as pid  # noqa: E402


class TestPinImageDigest(unittest.TestCase):
    def test_verify_no_pinned(self):
        # Test that verify returns error when no digest file exists
        with tempfile.TemporaryDirectory() as d:
            old_file = pid.DIGEST_FILE
            pid.DIGEST_FILE = Path(d) / "nonexistent.json"
            result = pid.verify_digest()
            self.assertEqual(result["status"], "error")
            pid.DIGEST_FILE = old_file

    def test_pin_and_verify(self):
        # Mock the digest retrieval
        old_get = pid.get_image_digest
        pid.get_image_digest = lambda: "sha256:testdigest123"
        with tempfile.TemporaryDirectory() as d:
            old_file = pid.DIGEST_FILE
            pid.DIGEST_FILE = Path(d) / "digest.json"
            result = pid.pin_digest()
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["digest"], "sha256:testdigest123")
            # Verify
            verify_result = pid.verify_digest()
            self.assertEqual(verify_result["status"], "ok")
            self.assertTrue(verify_result["match"])
            pid.DIGEST_FILE = old_file
        pid.get_image_digest = old_get


if __name__ == "__main__":
    unittest.main()