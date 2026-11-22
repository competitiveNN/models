import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADOPT_DIR = ROOT / "strata-old-source" / "terminal" / "strata_cli" / "launch"
SERVE_DIR = ROOT / "strata-old-source" / "terminal" / "serve"
SCRIPTS_DIR = ROOT / "scripts"

sys.path.insert(0, str(ADOPT_DIR))
sys.path.insert(0, str(ROOT / "strata-old-source" / "terminal"))

import adopt  # noqa: E402


class TestGpuRolesAndFailover(unittest.TestCase):
    """Behavioral tests for the 2x B580 TP2 GPU-role assignment and failover logic."""

    def test_gpu_role_assignment_tp2(self):
        """Verify 2x B580 TP2 runconfig assigns main and helper roles correctly."""
        config = {
            "model": "swift",
            "gpu": [0, 1],
            "layer_split": "auto",
            "args": ["--gpu", "0,1", "--stream-experts", "--layer-split", "auto"],
        }
        self.assertEqual(config["gpu"], [0, 1])
        self.assertIn("--gpu", config["args"])
        self.assertIn("0,1", config["args"])
        self.assertEqual(config["layer_split"], "auto")

    def test_engine_order_helpers_first_main_last(self):
        """TP2 engine order must be helpers (slowest first) then main last."""
        from strata_control import gpu_roles  # noqa: E402

        roles = {0: "helper", 1: "main"}
        order = gpu_roles.order(roles, [{"index": 0}, {"index": 1}])
        self.assertEqual(order, [0, 1])

        roles = {0: "main", 1: "helper"}
        order = gpu_roles.order(roles, [{"index": 0}, {"index": 1}])
        self.assertEqual(order, [1, 0])  # helper first, main last

    def test_failover_recovery_config(self):
        """Server reasoning loop recovery default protects against artifact loops."""
        server_py = SERVE_DIR / "server.py"
        content = server_py.read_text(encoding="utf-8", errors="replace")
        self.assertIn("reasoning_loop_recovery", content)
        self.assertIn("recover", content)

    def test_saved_roles_gpu_hand_edited_ignores_roles(self):
        """A hand-edited 'gpu' wins over saved roles (gpu_roles ignored)."""
        from strata_control import gpu_roles  # noqa: E402

        cfg = {
            "gpu_roles": {"0": "helper", "1": "main"},
            "gpu": [0, 1],  # engine order = helpers first (0), main last (1) -> roles honored
        }
        roles, problem = gpu_roles.saved_roles(cfg)
        self.assertIsNone(problem)
        self.assertEqual(roles, {0: "helper", 1: "main"})

        cfg["gpu"] = [1, 0]  # hand-edited: engine order [1,0] != mirror [0,1] -> roles ignored
        roles, problem = gpu_roles.saved_roles(cfg)
        self.assertIsNotNone(problem)
        self.assertIsNone(roles)

    def test_tp2_two_cards_b580(self):
        """Two identical 12 GB B580 cards: identical speed -> highest-number card is Main."""
        from strata_control import gpu_roles  # noqa: E402

        cards = [
            {"index": 0, "name": "Intel Arc B580", "vram_gb": 12.0, "speed": 1.0},
            {"index": 1, "name": "Intel Arc B580", "vram_gb": 12.0, "speed": 1.0},
        ]
        rec = gpu_roles.recommend(cards)
        main = rec["main"]
        self.assertEqual(main, 1)  # identical cards: highest number is Main

    def test_adopt_find_ple_shard(self):
        """Swift stores per_layer_token_embd.weight in shard 1; find_ple_shard must find it."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            shard1 = base / "model-00001-of-00002.gguf"
            shard2 = base / "model-00002-of-00002.gguf"
            shard1.write_bytes(b"no marker here")
            shard2.write_bytes(b"per_layer_token_embd.weight found")
            self.assertEqual(adopt.find_ple_shard([shard1, shard2]), shard2)


if __name__ == "__main__":
    unittest.main()
