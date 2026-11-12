# Mitigation Paths & Future Architecture Work: Dual-B580 TP2 Strata

## Executive Summary

The dual-GPU TP=2 target (≥40 tok/s decode, ≥1400 tok/s prefill) is currently **architecturally unachievable**
on the Strata SYCL/Level Zero port. This document outlines the concrete work items needed to unblock
TP=2 tensor parallelism and reach the performance targets on dual Intel Arc B580 GPUs.

---

## 1. Implement SYCL Port of Peer Experts (TP=2 Weight Sharding)

### Current State

`strata-src/sycl/src/core/peer_experts.cpp` explicitly stubs out multi-GPU expert tier:

```cpp
bool PeerExperts::open(...) {
    err = "--peer-device: the second-GPU expert tier is not ported to SYCL yet";
    return false;
}
```

Upstream CUDA implementation routes expert weights to a second GPU as an expert-cache tier.
The SYCL port does not exist.

### Required Work

| Task | File | Description |
|------|------|-------------|
| Implement `PeerExperts::open()` for SYCL | `peer_experts.cpp` | Initialize second GPU context, allocate peer-expert VRAM |
| Implement `PeerExperts::launch()` for SYCL | `peer_experts.cpp` | Launch expert computation on peer device |
| Implement `PeerExperts::finish()` for SYCL | `peer_experts.cpp` | Synchronize and collect results from peer |
| Add `--peer-device` CLI flag | `server_intel.py`, config parser | Expose peer-device option to users |
| Test with Level Zero | Integration | Validate on dual B580 hardware |

### Upstream Reference

The CUDA implementation in `src/core/peer_experts.cpp` (upstream) provides the reference
design. Key concepts:
- Second GPU as expert-cache tier (not full model replica)
- Expert weights sharded/routed across both GPUs
- PCIe transfer only for cross-GPU expert fetches (not all experts)

### Estimated Impact

Enabling true TP=2 would:
- Shard 12,925 experts across both GPUs (~6,462 per GPU)
- Reduce PCIe expert streaming from 18.73 GiB to near-zero
- Potentially achieve ≥40 tok/s decode / ≥1400 tok/s prefill on dual B580

---

## 2. Generate Strata Data Packs for Smaller Models

### Current State

Only one Strata data pack exists locally: `swift-iq3_xxs` (72B IQ3_XXS).
Smaller GGUFs available but without packs:
- Qwen3.5-0.8B (~504 MB)
- Qwen3.5-9B (~6.3 GB)
- gemma-4-E2B-it (~1.1 GB)
- LFM2.5-1.2B (~698 MB)

### Required Work

| Task | Description |
|------|-------------|
| Build pack generator | Tool to convert GGUF + routing data into Strata binary pack format |
| Generate packs for 7B-14B models | `experts.bin`, `native_experts.txt`, `dense.bin`, `conversions.json` |
| Validate pack loading | Test engine initialization with each pack |

### Estimated Impact

Smaller models (7B-14B) fit entirely in 12GB VRAM, eliminating PCIe expert streaming.
Expected decode: 30-60 tok/s on single B580. With TP=2 sharding, potentially ≥40 tok/s.

---

## 3. Fix Level Zero Verify Window Device Loss

### Current State

`UR_RESULT_ERROR_DEVICE_LOST` at `verify.cpp:2820` when:
- VRAM pressure leaves <600 MiB free
- Verify window allocates device buffers for expert computation
- Level Zero queue synchronization stalls under async PCIe expert streaming

### Required Work

| Task | File | Description |
|------|------|-------------|
| Add drain timeout with retry | `verify.cpp:343-370` (`release_gpu_waits`) | Retry with backoff instead of immediate failure |
| VRAM headroom guard | `weights.cpp` | Refuse to load if projected free VRAM < threshold |
| Expert cache eviction policy | `expert_cache.cpp` | LRU eviction to prevent VRAM exhaustion |
| Level Zero queue sync fix | `copy_queue.cpp` | Use blocking wait instead of polling for lost device |

### Estimated Impact

Would improve stability but NOT throughput. Necessary prerequisite for any multi-GPU work.

---

## 4. Build Containerized strata-server Image

### Current State

`localhost/strata-server:latest` image exists (86.2 GB) at `/var/home/fra/dev/models/strata-setup`.
Containerfile.strata defines the build.

### Required Work

| Task | Description |
|------|-------------|
| Optimize image size | Remove unnecessary build artifacts, use multi-stage build |
| Pin Level Zero driver version | Ensure Battlemage compatibility |
| Add health check endpoint | `/health` returns `"loaded": true` when model ready |
| Automated build pipeline | `docker build` + tag + push to localhost registry |

---

## Priority Ranking

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P0 | Fix Level Zero device loss | Medium | Unblocks all inference |
| P0 | Implement SYCL peer-experts | High | Enables TP=2, eliminates PCIe streaming |
| P1 | Generate 7B-14B Strata packs | Medium | Enables smaller models in VRAM |
| P1 | Optimize container image | Low | Deployment readiness |
| P2 | Drain timeout with retry | Low | Stability improvement |

---

## Success Criteria

With all P0/P1 items complete:

| Metric | Target | Current |
|--------|--------|---------|
| Decode tok/s (dual GPU TP=2) | ≥40 | 0.0 (crash) |
| Prefill tok/s (dual GPU TP=2) | ≥1400 | 0.0 (crash) |
| VRAM free after load | >2000 MiB | <600 MiB |
| Verify window stability | No device loss | Crashes at load |

---
