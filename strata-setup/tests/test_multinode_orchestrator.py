import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import multinode_orchestrator as mn  # noqa: E402


class TestMultinodeOrchestrator(unittest.TestCase):
    def test_cluster_status(self):
        orch = mn.ClusterOrchestrator()
        orch.add_node(mn.NodeInfo("node-0", "192.168.1.100", 1235, 2, True))
        orch.add_node(mn.NodeInfo("node-1", "192.168.1.101", 1235, 2, True))
        status = orch.cluster_status()
        self.assertEqual(status["total_nodes"], 2)
        self.assertEqual(status["healthy_nodes"], 2)
        self.assertEqual(status["total_gpus"], 4)
        self.assertEqual(status["tp2_instances"], 2)

    def test_failover(self):
        orch = mn.ClusterOrchestrator()
        orch.add_node(mn.NodeInfo("node-0", "192.168.1.100", 1235, 2, True))
        orch.add_node(mn.NodeInfo("node-1", "192.168.1.101", 1235, 2, True))
        orch.mark_unhealthy("node-1")
        status = orch.cluster_status()
        self.assertEqual(status["healthy_nodes"], 1)
        self.assertEqual(status["total_gpus"], 2)
        self.assertEqual(status["tp2_instances"], 1)

    def test_node_removal(self):
        orch = mn.ClusterOrchestrator()
        orch.add_node(mn.NodeInfo("node-0", "192.168.1.100", 1235, 2, True))
        self.assertTrue(orch.remove_node("node-0"))
        self.assertFalse(orch.remove_node("node-0"))
        self.assertEqual(orch.cluster_status()["total_nodes"], 0)


if __name__ == "__main__":
    unittest.main()