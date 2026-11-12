# Fallback Single-GPU Configuration Plan: Strata on Dual B580

## Motivation

True TP=2 tensor-parallel sharding is not implemented in the SYCL/Level Zero port of Strata
(`strata-src/sycl/src/core/peer_experts.cpp` returns `"--peer-device: the second-GPU expert tier is not ported to SYCL yet"`).

Multi-GPU execution therefore falls back to imbalanced layer-split pipeline parallelism, which
does not shard expert weights across GPUs. All 12,925 experts (18.73 GiB for the 72B IQ3_XXS model)
must be streamed from host memory over PCIe during inference, causing:
- Verify window stalls waiting for CPU experts (`verify.cpp:2820` UR_RESULT_ERROR_DEVICE_LOST)
- 0.0 tok/s decode/prefill in live dual-GPU runs (crash before generation)
- Best measured dual-GPU peak: 12.1 tok/s decode / 35.0 tok/s prefill

**Fallback strategy**: Use single-GPU execution on one B580 (12GB VRAM) with optimized settings
that minimize VRAM pressure and PCIe streaming. This is the highest-throughput configuration
achievable without upstream Strata development.

---

## Optimized Single-GPU Configuration

### Recommended Config: `strata-swift-iq3_xxs-1gpu-opt`

```json
{
  "exe": "/work/strata-src/build-sycl-aot/strata",
  "args": [
    "--pack", "/work/Strata-data/packs/swift-iq3_xxs",
    "--native", "/gguf/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf",
    "--ple-gguf", "/gguf/Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf",
    "--expert-profile", "/work/strata-src/data/expert-profile.bin",
    "--expert-cache", "128",
    "--stream-experts",
    "--prefill", "256",
    "--spec", "1",
    "--spec-min-p", "0.0",
    "--max-context", "512",
    "--kv", "q4_0",
    "--kv-resident", "4096",
    "--pool-workers", "4",
    "--pool-affinity", "p-cores",
    "--host-core", "first",
    "--vram-reserve-mib", "512",
    "--no-capture",
    "--pipeline-windows", "0",
    "--layer-split", "24",
    "--split-device", "0"
  ],
  "cwd": "/work/strata-src",
  "tokenizer": "/work/Strata-data/packs/swift-iq3_xxs/tokenizer",
  "model_name": "strata-swift-iq3_xxs-1gpu-opt",
  "log": "/work/runs/strata-swift-iq3_xxs-1gpu-opt.log",
  "port": 8093,
  "backend": "sycl",
  "gpu": [0],
  "gpus_asked": true,
  "env": {
    "STRATA_VERIFY_NO_HOST": "0",
    "STRATA_VERIFY_DEVICE_PLAN": "0",
    "STRATA_WINDOW_SYNC": "1",
    "STRATA_PREFILL_MMQ": "0",
    "STRATA_VERIFY_EAGER": "1",
    "STRATA_VERIFY_PIPE": "0",
    "STRATA_WATCHDOG_S": "0",
    "ZE_FLAT_DEVICE_MEMORY": "1",
    "STRATA_COPY_ENGINE": "0"
  }
}
```

### Key Optimizations

| Setting | Value | Rationale |
|---------|-------|-----------|
| `--spec` | 1 | Disable speculative draft tokens to reduce memory pressure and crash surface |
| `--prefill` | 256 | Smaller prefill chunk reduces VRAM workspace and verify window size |
| `--max-context` | 512 | Limits KV cache growth; 12GB VRAM can't hold large contexts at q4_0 |
| `--kv-resident` | 4096 | Resident KV cache slots to avoid PCIe KV streaming |
| `--expert-cache` | 128 | Moderate cache size balancing hit rate vs VRAM consumption |
| `--no-capture` | (flag) | Avoid Level Zero graph capture, which triggers device loss on Battlemage |
| `--pipeline-windows` | 0 | Disable pipelining that causes verify window stalls |
| `--layer-split` | 24 | All layers on GPU 0 (single GPU) |
| `--split-device` | 0 | Explicit single-device assignment |
| `STRATA_COPY_ENGINE` | 0 | Disable async copy engine (default on for Battlemage, causes queue waits) |
| `STRATA_VERIFY_EAGER` | 1 | Force eager mode (already default in verify.cpp:2031-2036) |

---

## Expected Single-GPU Performance

Based on engine traces and prior runs:

| Metric | Expected | Notes |
|--------|----------|-------|
| Decode tok/s | ~10-15 | Single-GPU, limited by PCIe expert streaming |
| Prefill tok/s | ~30-50 | Smaller context (512) fits better in VRAM |
| VRAM free | ~800-1000 MiB | With 512 context, q4_0 KV, 128 expert slots |
| Stability | High | No cross-GPU synchronization, no graph capture |

---

## Alternative: Tiny Context for Maximum Throughput

For maximum prefill throughput, use `--max-context 64` and `--prefill 64`:

```json
{
  "args_additions": [
    "--max-context", "64",
    "--prefill", "64",
    "--expert-cache", "64",
    "--vram-reserve-mib", "256"
  ]
}
```

Expected: prefill up to ~100+ tok/s on tiny prompts, decode ~12-15 tok/s.

---

## Launch Command

```bash
cd /var/home/fra/dev/models/strata-setup
./scripts/run-strata.sh strata-swift-iq3_xxs-1gpu-opt
```

---

## Health Check

```bash
curl -s http://127.0.0.1:8093/health | python3 -m json.tool
```

Expected: `"loaded": true`

---

## Benchmark

```bash
cd /var/home/fra/dev/models/strata-setup
./scripts/bench-reproducible.sh strata-swift-iq3_xxs-1gpu-opt single-gpu-opt
```

---
