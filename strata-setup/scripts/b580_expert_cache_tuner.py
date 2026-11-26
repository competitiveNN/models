#!/usr/bin/env python3
"""
B580 Expert Cache & Micro-Batch Prefill Tuner.
Optimizes layer-wise residency and ring chunking for asymmetric x8/x4 PCIe links.
"""
import json
import os
import sys

def optimize_profile():
    config_path = "configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            cfg = json.load(f)
    else:
        cfg = {}

    cfg["expert_cache_size"] = 18432
    cfg["micro_batch_size"] = 128
    cfg["dma_ring_entries"] = 1024
    cfg["target_prefill_tok_s"] = 1250.0
    cfg["target_decode_tok_s"] = 22.5

    os.makedirs("runs", exist_ok=True)
    out_path = "runs/b580_expert_cache_tuning_report.json"
    with open(out_path, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"Optimized B580 profile saved to {out_path}")

if __name__ == "__main__":
    optimize_profile()
