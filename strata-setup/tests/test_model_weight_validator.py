import unittest
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import model_weight_validator as mv  # noqa: E402


class TestModelWeightValidator(unittest.TestCase):
    def test_validate_shards(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            shard1 = base / "model-00001-of-00002.gguf"
            shard2 = base / "model-00002-of-00002.gguf"
            shard1.write_bytes(b"per_layer_token_embd.weight here")
            shard2.write_bytes(b"no marker here")
            result = mv.validate_model_shards(base)
            self.assertTrue(result["valid"])
            self.assertEqual(result["shard_count"], 2)
            self.assertIn("model-00001", result["ple_shard"])

    def test_incomplete_shards(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "model-00001-of-00002.gguf").write_bytes(b"x")
            result = mv.validate_model_shards(base)
            self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()