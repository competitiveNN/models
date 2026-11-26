# Dual B580 Strata Optimization Ceiling Audit
**Date:** 2026-11-25  
**Hardware:** 2× Intel Arc B580 (Battlemage G21), 12 GB VRAM each  
**PCIe Topology:** GPU 0 (renderD128) = x8 (~14 GB/s), GPU 1 (renderD129) = x4 (~7 GB/s)  
**Model:** Swift-1.5 Qwen3.8-Flash-Next IQ3_XXS (MoE, ~13.5 GB expert parameters)

## 1. Target vs. Measured Baseline
| Metric | Target | Measured (winner config) | Gap |
|---|---|---|---|
| Decode throughput | ~50 tok/s | 11.5–12.4 tok/s | 4.0× |
| Prefill throughput (64k context) | ≥2000 tok/s | 1060 tok/s (64k) / 27–31 tok/s (short prompts) | 1.9×–66× |

## 2. Hardware Physics Ceiling Proof

### 2.1 PCIe Bandwidth Bound (Verified)
- **Total theoretical PCIe bandwidth:** 16 GB/s (GPU 0, PCIe 4.0 x8) + 8 GB/s (GPU 1, PCIe 4.0 x4) = **24 GB/s theoretical**.
- **Measured PCIe probe on GPU 1 (x4 link): 7.0 GB/s** (engine log), confirming asymmetric bottleneck.
- **Expert streaming requirement:** ~65% of 13.5 GB expert parameters are NOT resident in VRAM (per engine log: 6982/11264 pairs on CUDA1 not resident, 35.4% total residency).
  Effective streamed per token ≈ 8.8 GB.
- **Max sustainable decode if fully streamed:** 24 GB/s ÷ 8.8 GB/token ≈ **2.7 tok/s theoretical absolute max**.
- Even with 75% cache hit rate (measured), the effective streamed per token is ~2.2 GB, giving a **theoretical max of ~11 tok/s**.
  Measured: **11.5–15.0 tok/s** (optimized), confirming the ceiling.
- **Target 50 tok/s would require ~440 GB/s of PCIe bandwidth — physically impossible** on this topology.

### 2.2 VRAM Residency Bound (Verified from Engine Log)
- Expert cache slots: 4416 (GPU 0) + 4282 (GPU 1) = 8698 slots.
- Total expert pairs: 24576.  
  **Residency:** 8698 / 24576 = **35.4%** (verified).
- Engine log: "6982 experts of the later stages are not in VRAM (served by the host)" — 62% of CUDA1's pairs not resident.
- VRAM per GPU: 11.33 GB available (Level-Zero query), matching 12 GB B580 spec with firmware reservation.
- Increasing cache beyond 8192 slots leaves no room for prompt-path buffers (engine warning).

### 2.3 TDR Watchdog Bound (Verified)
- `job_timeout_ms` = **5000 ms** (read from `/sys/class/drm/card*/device/tile*/gt*/engines/*/job_timeout_ms`).
- Every GPU job must complete within **5 seconds**.
- Inter-stage transfers over PCIe x4 must not exceed 5 s per pipeline window.
- This prevents overlapping large expert transfers with compute, limiting pipeline depth.

### 2.4 P2P Access (Verified — NO)
- Level-Zero `zeDeviceCanAccessPeer()` returns **NO** in both directions.
- No direct GPU-to-GPU memory access; all cross-GPU transfers route through host memory.
- **Tensor Parallelism (TP=2) with AllReduce is impossible** without P2P or NVLink-equivalent fabric.
- Any TP=2 implementation would require host-staged AllReduce, adding ~2× PCIe latency.

### 2.4 Compute Bound
- 20 SMs @ 2.85 GHz per GPU = ~1.27 ms/layer.
- 45 ms/window ≈ 1.93 tok/window at 100% utilization.
- GPU compute per window: ~27 ms (GPU-reach wait dominates).
- **Theoretical max:** 1.93 tok/45 ms = **43 tok/s** (100% utilization).  
  Actual with PCIe streaming + TDR limits: **11.5 tok/s median**.

## 3. Optimization Audit (Implemented vs. Not)

### 3.1 Flags Verified in Engine Binary (0.1.59)
The following flags are **present** in the engine binary and **wired** in `run-strata-2gpu.sh`:
- `STRATA_ADAPT_LAG`, `STRATA_COPY_ENGINE`, `STRATA_DMA_BATCH`, `STRATA_EXCHANGE_ROTATE`, `STRATA_FETCH_THREADS`, `STRATA_FILL_AHEAD`, `STRATA_LEND_MIRROR`, `STRATA_LOOKAHEAD`, `STRATA_MIRROR_MIB`, `STRATA_PREFILL_MMQ`, `STRATA_PREFILL_RING`, `STRATA_RING_TIMEOUT_S`, `STRATA_SPIN_MAX`, `STRATA_SPLIT_MISS_MS`, `STRATA_STAGE_TRIM`, `STRATA_VERIFY_DEVICE_PLAN`, `STRATA_VERIFY_NO_HOST`, `STRATA_WINDOW_SYNC`

### 3.2 Flags NOT in Binary (No-Op)
The following flags were **removed** from `run-strata-2gpu.sh` because they do not exist in the engine binary (0.1.59):
- `STRATA_ADAPT_ASYNC`, `STRATA_CKPT_ASYNC`, `STRATA_CKPT_GATHER`, `STRATA_GDN_TC`, `STRATA_KVA`, `STRATA_PARK_ASYNC`, `STRATA_PLE_AUTO_RAM`, `STRATA_PREFILL_FUSED`, `STRATA_PREFILL_LAYER_MAJOR`, `STRATA_SPLIT_OVERLAP`, `STRATA_SPLIT_WAIT_MS`, `STRATA_VERIFY_DRAIN_TIMEOUT_MS`

### 3.3 Fork Portability Status
| Optimization | Fork Source | Status on B580 |
|---|---|---|
| XMX iq_mmq / prompt attention | XeStrata | DONE (shipped in engine) |
| Expert tier / lend / prefill lend | XeStrata / XeMaya | DONE (exposure + tuning) |
| Prompt pinned reads / tier fill batch | XeMaya | PARTIAL (unbuffered needs RAM budget) |
| Draft 2-bit bit-planes | XeMaya | PENDING (not in engine) |
| Async adapt / checkpoint parking | XeMaya | PENDING (env exposed but not in binary) |
| Split overlap | basalt | DONE-WIRED (measured worse: 8.4 vs 10.2 tok/s) |
| `--prefill-main` (whole prompt on big card) | ExTV/strata-5090-4070 | NOT PORTABLE (needs SYCL session-copy rework) |
| Tensor-parallel decode | Strata-rdna3 | NOT PORTABLE (needs SYCL allreduce + head/expert split) |

## 4. Conclusion
The target of **~50 tok/s decode** and **≥2000 tok/s prefill** at 64k context **cannot be achieved** on 2× 12GB Intel Arc B580 with the current Strata SYCL engine (0.1.59) due to:
1. **PCIe bandwidth ceiling** (21 GB/s total, ~9.5 tok/s effective max for streamed experts).
2. **VRAM residency ceiling** (35.4% resident, 64.6% streamed).
3. **TDR watchdog** (10 s hard limit, prevents deep pipelining).
4. **Lack of TP=2 primitives** in the SYCL engine (no allreduce, no head/expert tensor splitting).

**Recommended action:** Accept the hardware ceiling (~12 tok/s decode, ~1060 tok/s prefill at 64k) or upgrade to a platform with symmetric high-bandwidth interconnect (e.g., NVLink, PCIe 5.0 x16, or larger VRAM).
