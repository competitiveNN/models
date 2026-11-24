"""Unit tests for provenance recording in scripts/sweep-one.py."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sweep_one", ROOT / "scripts" / "sweep-one.py")
sweep_one = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep_one)


class TestGetProvenance(unittest.TestCase):
    def test_returns_git_commit_and_image_digest(self):
        prov = sweep_one.get_provenance()
        self.assertIsInstance(prov, dict)
        self.assertIn("git_commit", prov)
        self.assertIn("image_digest", prov)
        self.assertTrue(prov["git_commit"])
        self.assertTrue(prov["image_digest"].startswith("sha256:"))

    def test_returns_none_without_git_or_digest(self):
        with mock.patch.object(sweep_one, "ROOT", Path("/nonexistent-root")):
            with mock.patch("subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
                self.assertIsNone(sweep_one.get_provenance())

    def test_git_failure_omits_git_commit(self):
        digest_file = ROOT / "configs" / "strata-old-image-digest.json"
        original = digest_file.read_text() if digest_file.exists() else None
        try:
            digest_file.write_text(json.dumps({"digest": "sha256:testdigest"}))
            with mock.patch("subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not a repo")
                prov = sweep_one.get_provenance()
            self.assertIsNotNone(prov)
            self.assertNotIn("git_commit", prov)
            self.assertEqual(prov["image_digest"], "sha256:testdigest")
        finally:
            if original is None:
                digest_file.unlink(missing_ok=True)
            else:
                digest_file.write_text(original)

    def test_missing_digest_omits_image_digest(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(sweep_one, "ROOT", Path(td)):
                with mock.patch("subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr="")
                    prov = sweep_one.get_provenance()
            self.assertEqual(prov, {"git_commit": "abc123"})


if __name__ == "__main__":
    unittest.main()
