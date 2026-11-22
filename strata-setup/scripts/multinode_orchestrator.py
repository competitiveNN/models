#!/usr/bin/env python3
"""Multi-node scaling orchestration helper for Strata B580 TP2 clusters.

Provides coordination primitives for scaling inference across multiple machines,
each with 2x Intel Arc B580 GPUs running Tensor Parallel 2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class NodeInfo:
    """Represents a single node in the cluster."""

    def __init__(self, node_id: str, host: str, port: int, gpus: int = 2, healthy: bool = True):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.gpus = gpus
        self.healthy = healthy

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "gpus": self.gpus,
            "healthy": self.healthy,
            "url": f"http://{self.host}:{self.port}/v1/chat/completions",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeInfo":
        return cls(
            node_id=data["node_id"],
            host=data["host"],
            port=data["port"],
            gpus=data.get("gpus", 2),
            healthy=data.get("healthy", True),
        )


class ClusterOrchestrator:
    """Orchestrates multiple Strata nodes for distributed inference."""

    def __init__(self, nodes: list[NodeInfo] | None = None):
        self.nodes = nodes or []

    def add_node(self, node: NodeInfo) -> None:
        self.nodes.append(node)

    def remove_node(self, node_id: str) -> bool:
        for i, n in enumerate(self.nodes):
            if n.node_id == node_id:
                self.nodes.pop(i)
                return True
        return False

    def get_healthy_nodes(self) -> list[NodeInfo]:
        return [n for n in self.nodes if n.healthy]

    def total_gpus(self) -> int:
        return sum(n.gpus for n in self.get_healthy_nodes())

    def total_tp2_instances(self) -> int:
        return sum(n.gpus // 2 for n in self.get_healthy_nodes())

    def get_load_balancer_endpoints(self) -> list[str]:
        return [f"http://{n.host}:{n.port}/v1/chat/completions" for n in self.get_healthy_nodes()]

    def cluster_status(self) -> dict[str, Any]:
        healthy = self.get_healthy_nodes()
        return {
            "total_nodes": len(self.nodes),
            "healthy_nodes": len(healthy),
            "unhealthy_nodes": len(self.nodes) - len(healthy),
            "total_gpus": self.total_gpus(),
            "tp2_instances": self.total_tp2_instances(),
            "endpoints": self.get_load_balancer_endpoints(),
        }

    def mark_unhealthy(self, node_id: str) -> bool:
        for n in self.nodes:
            if n.node_id == node_id:
                n.healthy = False
                return True
        return False

    def mark_healthy(self, node_id: str) -> bool:
        for n in self.nodes:
            if n.node_id == node_id:
                n.healthy = True
                return True
        return False


def main() -> int:
    import json
    orchestrator = ClusterOrchestrator()
    orchestrator.add_node(NodeInfo("node-0", "192.168.1.100", 1235, 2, True))
    orchestrator.add_node(NodeInfo("node-1", "192.168.1.101", 1235, 2, True))
    print(json.dumps(orchestrator.cluster_status(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())