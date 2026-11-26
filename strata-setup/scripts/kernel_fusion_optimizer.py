#!/usr/bin/env python3
"""
Kernel fusion and DMA ring scheduler optimizer for Strata 2x B580.
Fine-tunes fusion flags and DMA staging thresholds for asymmetric PCIe x8/x4.
"""
import json
from pathlib import Path

CONFIG_PATH = Path("configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json")

def optimize_kernel_fusion():
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}")
        return
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env = cfg.setdefault("env", {})
    # Advanced kernel fusion tuning for asymmetric B580 x8/x4 PCIe
    env["STRATA_KV_HOST_DMA"] = "1"
    env["STRATA_ADAPT_OVERLAP"] = "1"
    env["STRATA_GR_FUSED"] = "1"
    env["STRATA_QSA_ROWS"] = "1"
    # Aggressive DMA staging for kernel-fused path
    env["STRATA_DMA_BATCH"] = "256"
    env["STRATA_PREFILL_RING"] = "1024"
    env["STRATA_STAGER_RING"] = "256"
    env["STRATA_MIRROR_MIB"] = "32768"
    env["STRATA_ASYNC_RING_BUFFER"] = "1"
    env["STRATA_MOE_DMA_OVERLAP"] = "1"
    env["STRATA_FETCH_THREADS"] = "32"
    env["STRATA_POOL_SPIN_US"] = "100"
    env["STRATA_PCIE_SPLIT_MODE"] = "asymmetric"
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("[kernel_fusion_optimizer] Successfully optimized config with advanced kernel fusion parameters.")

if __name__ == "__main__":
    optimize_kernel_fusion()
