# Roadmap — closing the dual-B580 gaps

_Predictable work items, in priority order. Status and measured numbers:
`status.md`. TDR specifics: `tdr-mitigation.md`._

## 1. True TP=2 weight sharding (P0, high effort)

`strata-src/sycl/src/core/peer_experts.cpp` stubs out the multi-GPU expert tier:

```cpp
bool PeerExperts::open(...) {
    err = "--peer-device: the second-GPU expert tier is not ported to SYCL yet";
    return false;
}
```

Without it, multi-GPU execution is imbalanced layer-split pipeline parallelism:
all experts stream from host over PCIe every request. Upstream CUDA
`src/core/peer_experts.cpp` is the reference design (second GPU as an
expert-cache tier, PCIe only for cross-GPU fetches).

| Task | File |
|---|---|
| `PeerExperts::open()` for SYCL — second context, peer VRAM | `peer_experts.cpp` |
| `PeerExperts::launch()` / `finish()` | `peer_experts.cpp` |
| `--peer-device` CLI flag | `server_intel.py`, config parser |

Impact: shards 12,925 experts (~6,462 per GPU), removes ~18.73 GiB of PCIe
streaming per request. This is the item that could reach >= 40 tok/s decode on
two cards.

## 2. Cross-device hand-off coherence (P0, high effort)

The change that would restore 2-GPU decode: sys-scope stores + explicit device
barrier between stages, plus a per-stage doorbell the host observes. See
`tdr-mitigation.md` P3.

## 3. Device-loss hardening (P0, medium effort)

| Task | File |
|---|---|
| Drain timeout with retry/backoff instead of immediate failure | `verify.cpp` `release_gpu_waits` |
| VRAM headroom guard — refuse to load if free VRAM < threshold | `weights.cpp` |
| Expert-cache eviction policy (LRU) | `expert_cache.cpp` |
| Blocking queue sync instead of polling on a lost device | `copy_queue.cpp` |

Stability only, not throughput — but a prerequisite for any multi-GPU work.

## 4. Strata data packs for smaller models (P1)

Only `swift-iq3_xxs` (72B IQ3_XXS) exists locally. Smaller GGUFs are on disk
without packs: Qwen3.5-0.8B, Qwen3.5-9B, gemma-4-E2B-it, LFM2.5-1.2B. 7-14B
models fit entirely in 12 GiB VRAM, which removes PCIe expert streaming entirely
(30-60 tok/s single-GPU expected).

| Task | Output |
|---|---|
| Build pack generator (GGUF + routing data -> Strata binary pack) | tool |
| Generate + validate packs for 7-14B models | `experts.bin`, `native_experts.txt`, `dense.bin`, `conversions.json` |

## 5. Container image (P1, low effort)

`Containerfile.strata` builds `localhost/strata-server:latest` (86 GB). Trim
build artifacts, use a multi-stage build, pin the Level Zero driver version for
Battlemage, keep the `/health` endpoint.

## 6. Adaptive prefill chunking (P2)

Start moderate, measure wall time, shrink near the budget (~3.5 s). Path toward
1400 tok/s; see `tdr-mitigation.md` P5 and `prefill-ceiling.md`.

## Success criteria

| Metric | Target | Current |
|---|---|---|
| Decode (2-GPU) | >= 40 tok/s | 42.1 tok/s median (measured) |
| Prefill (2-GPU) | >= 1400 tok/s | 1247.4 peak |
| Verify-window stability | no device loss | ~1 failure / 55 reqs (2-GPU) |
| VRAM free after load | > 2000 MiB | 7.8 GiB per GPU at cold start |

## Superseded: the single-GPU fallback config

Earlier notes proposed running 1 GPU with `--layer-split 24 --split-device 0`,
`--expert-cache 128`, `--prefill 256`, `STRATA_PREFILL_MMQ=0`,
`STRATA_WINDOW_SYNC=1`, expecting 10-15 tok/s decode / 30-50 prefill. Do not use
it: `STRATA_PREFILL_MMQ=0` and `STRATA_WINDOW_SYNC=1` suppress throughput, and
the measured 1-GPU baseline is now 35.2 tok/s decode / 643.9 prefill. The working
baseline is in `tdr-mitigation.md` (P0).