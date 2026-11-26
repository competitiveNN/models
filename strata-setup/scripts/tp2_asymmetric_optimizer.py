#!/usr/bin/env python3
"""
Asymmetric TP=2 ring buffer and kernel fusion optimizer for 2x B580.
Adjusts chunk sizes, ring occupancy, and host-DMA prefetch thresholds.
"""
import json
from pathlib import Path

CONFIG_PATH = Path("configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json")

def optimize_config():
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}")
        return
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env = cfg.setdefault("env", {})
    # Aggressive ring tuning for asymmetric x8/x4 PCIe
    env["STRATA_PREFILL_RING"] = "512"
    env["STRATA_STAGER_RING"] = "128"
    env["STRATA_DMA_BATCH"] = "128"
    env["STRATA_MIRROR_MIB"] = "16384"
    env["STRATA_ASYNC_RING_BUFFER"] = "1"
    env["STRATA_MOE_DMA_OVERLAP"] = "1"
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("[tp2_asymmetric_optimizer] Successfully optimized config with advanced ring parameters.")

if __name__ == "__main__":
    optimize_config()
