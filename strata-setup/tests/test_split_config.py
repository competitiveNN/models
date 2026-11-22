import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVE_DIR = ROOT / "strata-old-source" / "terminal" / "serve"
sys.path.insert(0, str(SERVE_DIR))

import split  # noqa: E402


class TestSplitConfigValidation(unittest.TestCase):
    def test_valid_split_spec(self):
        cfg = {"split_serve": {"prefill_gpu": 0, "decode_gpu": 1, "min_prompt_tokens": 1024}}
        spec = split.split_spec(cfg)
        self.assertEqual(spec["prefill_gpu"], 0)
        self.assertEqual(spec["decode_gpu"], 1)
        self.assertEqual(spec["min_prompt_tokens"], 1024)

    def test_same_card_raises_error(self):
        cfg = {"split_serve": {"prefill_gpu": 0, "decode_gpu": 0}}
        with self.assertRaises(split.SplitConfigError):
            split.split_spec(cfg)

    def test_forbidden_args_raises_error(self):
        cfg = {
            "split_serve": {"prefill_gpu": 0, "decode_gpu": 1},
            "args": ["--layer-split", "auto"]
        }
        spec = split.split_spec(cfg)
        with self.assertRaises(split.SplitConfigError):
            split.check_cfg(cfg, spec)


if __name__ == "__main__":
    unittest.main()
