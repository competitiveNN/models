import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADOPT_DIR = ROOT / "strata-old-source" / "terminal" / "strata_cli" / "launch"
sys.path.insert(0, str(ADOPT_DIR))

import adopt  # noqa: E402


class TestFindShards(unittest.TestCase):
    def test_complete_set(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            for i in (1, 2):
                (base / f"model-{i:05d}-of-00002.gguf").write_bytes(b"x")
            shards = adopt.find_shards(base)
            self.assertEqual([p.name for p in shards], ["model-00001-of-00002.gguf", "model-00002-of-00002.gguf"])

    def test_incomplete_set(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "model-00001-of-00002.gguf").write_bytes(b"x")
            self.assertEqual(adopt.find_shards(base), [])

    def test_single_file(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "only.gguf").write_bytes(b"x")
            self.assertEqual(adopt.find_single(base), [base / "only.gguf"])


class TestFindPleShard(unittest.TestCase):
    def test_finds_marker_in_first_shard(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            first = base / "model-00001-of-00002.gguf"
            second = base / "model-00002-of-00002.gguf"
            first.write_bytes(b"prefix per_layer_token_embd.weight suffix")
            second.write_bytes(b"no marker here")
            self.assertEqual(adopt.find_ple_shard([first, second]), first)

    def test_falls_back_to_last_shard(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            first = base / "model-00001-of-00002.gguf"
            second = base / "model-00002-of-00002.gguf"
            first.write_bytes(b"no marker")
            second.write_bytes(b"no marker either")
            self.assertEqual(adopt.find_ple_shard([first, second]), second)


if __name__ == "__main__":
    unittest.main()
