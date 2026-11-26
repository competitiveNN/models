# Advanced Kernel-Level Bypasses & Speculative Execution Strategy for Dual Arc B580

**Date:** 2026-11-25 (updated 2026-11-26 with engine-verification status)  
**Objective:** Document candidate bypass strategies and clearly separate **engine-verified/wired** knobs from **unverified/no-op placeholders** on the current Strata SYCL engine (0.1.59).

> **Verification note:** "Verified in binary/wired" means the flag appears in `run-strata-2gpu.sh` or engine logs/binary audit evidence recorded in `docs/B580_CEILING_AUDIT.md` and `docs/FORK_PORTS.md`. "Not in binary / no-op" means it was not present in the audited engine binary and should not be assumed effective.

---

## 1. Executive Strategy

Rather than treating PCIe bandwidth and VRAM residency as immutable bottlenecks, candidate software-side bypasses fall into four buckets:

1. **Speculative execution / draft overlap (MTP):** Amortize decode cost by validating multiple draft tokens.
2. **Aggressive quantization/layout:** Increase effective residency by reducing expert/KV footprint.
3. **Async ring-buffer/DMA staging:** Overlap host staging, PCIe DMA, and compute where engine supports it.
4. **Asymmetric stage balancing:** Shift work toward GPU0/x8 to reduce GPU1/x4 bottleneck impact.

---

## 2. Flag / Knob Verification Matrix

| Knob | Category | Status (0.1.59 audit) | Evidence | Notes |
|---|---|---|---|---|
| `--mtp on`, `--drafting auto`, `--set spec`, `--set spec-min-p` | Speculative decode | **Verified/wired** | `run-strata-2gpu.sh`, launch/config profiles | Effective only when draft/model support is present; acceptance rate hardware/model dependent. |
| `STRATA_PREFILL_RING`, `STRATA_STAGER_RING` | Host ring staging | **Verified/wired** | `run-strata-2gpu.sh`, kernel-fused-max profile | Larger rings improve staging headroom but increase host RAM pressure. |
| `STRATA_DMA_BATCH`, `STRATA_FETCH_THREADS` | DMA/fetch tuning | **Verified/wired** | `run-strata-2gpu.sh` | Tune cautiously; oversubscription can regress latency. |
| `STRATA_KV_PREFETCH`, `STRATA_IQ_PREFETCH`, `STRATA_CHUNKED_FILL`, `STRATA_PIPELINE_PRESTAGE`, `STRATA_DISJOINT_ADAPT` | Prefetch/pipeline overlap | **Verified/wired as env knobs** | `run-strata-2gpu.sh` | Behavior depends on engine implementation; measure with telemetry/audit before claiming gains. |
| `STRATA_WINDOW_SYNC=0` | Async window scheduling | **Verified/wired** | `run-strata-2gpu.sh` | Reduces blocking; validate coherence/stability after changes. |
| `STRATA_PREFILL_MMQ` | Prefill MMQ path | **Verified/wired** | `run-strata-2gpu.sh`, ceiling audit | `auto`/`1` profiles used in verified runs. |
| `STRATA_COPY_ENGINE` | Copy engine | **Verified/wired (off by default)** | `run-strata-2gpu.sh` | Keep default unless measured win on target workload. |
| `STRATA_LEND_MIRROR`, `STRATA_EXCHANGE_ROTATE`, `STRATA_PREFILL_HELP*` | Cross-stage lending/help | **Verified/wired** | `run-strata-2gpu.sh` | Can help asymmetric prefill; monitor for regressions. |
| `STRATA_MIRROR_MIB` | Host mirror budget | **Verified/wired** | `run-strata-2gpu.sh` | Large values consume host RAM; profile-dependent. |
| `STRATA_PCIE_SPLIT_MODE`, `STRATA_MOE_DMA_OVERLAP`, `STRATA_ASYNC_RING_BUFFER` | Advanced async DMA overlap | **Profile-present; engine effect unverified** | kernel-fused-max config, launch wiring added | Present in configs/wiring; not confirmed by 0.1.59 binary audit as effective. Treat as experimental until engine-source/binary confirms. |
| `STRATA_PREFILL_FUSED`, `STRATA_KVA`, `STRATA_GDN_TC`, `STRATA_PREFILL_LAYER_MAJOR` | Kernel fusion/layout bypasses | **Not in audited binary / no-op** | `docs/B580_CEILING_AUDIT.md` no-op list | Do not count as active optimizations; remove from performance claims. |
| `STRATA_SPLIT_OVERLAP` | Split overlap | **Tested & rejected** | `docs/FORK_PORTS.md` | Measured worse decode (8.4 vs 10.2 tok/s) due B580 queue overhead. |
| TP=2 / AllReduce / head+expert tensor split | Multi-GPU parallelism | **Not portable / infeasible** | `docs/B580_CEILING_AUDIT.md`, `docs/FORK_PORTS.md` | No L0 P2P; SYCL engine lacks TP primitives. |

---

## 3. Kernel-Level / Scheduler Bypasses (Actionable)

### 3.1 Async expert prefetch and staging
- **Use:** `STRATA_KV_PREFETCH=1`, `STRATA_IQ_PREFETCH=1`, `STRATA_CHUNKED_FILL=1`, `STRATA_PIPELINE_PRESTAGE=1`.
- **Goal:** Hide PCIe latency behind compute by pre-staging expert/KV data.
- **Measure:** decode tok/s, 64k prefill tok/s, coherence, telemetry PCIe/TDR, and regression gate.

### 3.2 Ring-buffer / DMA staging expansion (profile-gated)
- **Use:** `--kernel-fused-max` or env overrides (`STRATA_PREFILL_RING`, `STRATA_STAGER_RING`, `STRATA_MIRROR_MIB`, `STRATA_DMA_BATCH`, `STRATA_FETCH_THREADS`).
- **Goal:** Reduce staging backpressure on large prompt ingest.
- **Risk:** Host RAM exhaustion, increased tail latency, or no gain if engine ignores knobs.

### 3.3 Window sync bypass
- **Use:** `STRATA_WINDOW_SYNC=0`.
- **Goal:** Avoid unnecessary pipeline bubbles.
- **Risk:** Requires coherence/stability validation.

## 4. Speculative Drafting / MTP

- **Use:** `MTP=on`, `DRAFTING=auto`, tune `SPEC` and `SPEC_MIN_P`.
- **Reality:** MTP can improve effective throughput when acceptance is high, but does not remove PCIe/residency ceilings for expert-stream-bound decode.
- **Validation:** compare median decode/prefill/coherence against baseline profile with identical context and prompt set.

## 5. Quantization / Residency

- **Use:** IQ3_XXS (current), KV `int8`/`int4` profile-specific, expert-cache sizing within VRAM budget.
- **Reality:** Larger expert cache improves residency but competes with prompt/KV/pipeline buffers; engine warns when cache leaves no prompt-path room.
- **Not a silver bullet:** 35.4% residency was measured in audited runs; full residency is not possible on 2×12 GB for this model.

## 6. Implementation / Execution Roadmap

1. **Wire reproducible profiles:** keep kernel-fused-max defaults in `run-strata-2gpu.sh` and config JSON. *Done in this pass.*
2. **Collect evidence:** run `scripts/b580_advanced_telemetry.py` before/after experiments; archive snapshots.
3. **Gate regressions:** run `scripts/strata_regression_audit.py` with explicit targets; treat exit 2 as hardware-ceiling/regression signal, not script failure.
4. **Validate no-op claims:** any new flag must be confirmed in engine binary/source before being described as active.
5. **Future engine work:** only source-level SYCL changes can validate unverified async DMA overlap knobs or add TP primitives.

## 7. Current Measured Reality

| Metric | Target | Measured | Status |
|---|---:|---:|---|
| Single-stream decode | 50 tok/s | ~15.5 tok/s (kernel-fused-max), 24.3 tok/s (audit snapshot) | hardware-bounded |
| 64k prefill | 2000 tok/s | ~1000 tok/s | hardware-bounded |
| Aggregate `--parallel 8` | maximize | ~119 tok/s | useful throughput mode, different SLA |

The correct next step is disciplined, evidence-backed profiling and reproducible gating—not claiming no-op flags as performance wins.
