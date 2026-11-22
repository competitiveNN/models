#!/usr/bin/env python3
"""VRAM balancing and capacity estimator for multi-GPU TP2 Strata setups.

Calculates expected VRAM allocation and reserve margins for 2x Intel Arc B580 12GB
under different context windows and quantization levels.
"""
from __future__ import annotations

import sys
from typing import Any


def estimate_vram_allocation(context_tokens: int = 65536, kv_bits: int = 8, gpus: int = 2, card_vram_gb: float = 12.0) -> dict[str, Any]:
    # Approximate model weight size for Swift IQ3_XXS (~3.8B active) ~ 2.1 GB
    model_weight_gb = 2.1
    # KV cache size at 65536 ctx, int8 (~1 KB/token/layer or similar scale)
    kv_cache_gb = (context_tokens * kv_bits * 32 * 2) / (8 * (1024**3)) * 4  # scale factor
    total_needed_gb = model_weight_gb + kv_cache_gb
    per_gpu_allocated_gb = total_needed_gb / gpus
    reserve_gb = card_vram_gb - per_gpu_allocated_gb

    return {
        "context_tokens": context_tokens,
        "gpus": gpus,
        "card_vram_gb": card_vram_gb,
        "estimated_weight_gb": model_weight_gb,
        "estimated_kv_gb": round(kv_cache_gb, 2),
        "total_estimated_gb": round(total_needed_gb, 2),
        "per_gpu_gb": round(per_gpu_allocated_gb, 2),
        "estimated_reserve_gb": round(reserve_gb, 2),
        "fits": reserve_gb >= 0.25,  # require at least 256 MiB reserve
    }


def main():
    import json
    res = estimate_vram_allocation()
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
