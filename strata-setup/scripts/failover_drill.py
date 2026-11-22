#!/usr/bin/env python3
"""Automated failover drill verification for 2x Intel Arc B580 TP2 inference.

Validates expected recovery behaviors and role fallback logic for the
dual-GPU Strata setup when a GPU becomes unavailable or roles are degraded.
"""
from __future__ import annotations

import sys
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import vram_balancer  # noqa: E402


def run_failover_drill(gpus: int = 2) -> dict[str, Any]:
    if gpus < 2:
        return {"status": "degraded", "mode": "single-gpu-fallback", "viable": True}
    # Simulate failure of helper GPU
    remaining = gpus - 1
    reserve_ok = vram_balancer.estimate_vram_allocation(context_tokens=32768, kv_bits=8, gpus=remaining, card_vram_gb=12.0)["fits"]
    return {
        "status": "recovered" if reserve_ok else "failed",
        "mode": "single-gpu-fallback" if reserve_ok else "oom-risk",
        "remaining_gpus": remaining,
        "viable": reserve_ok,
    }


def main():
    import json
    res = run_failover_drill(2)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
