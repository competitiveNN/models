# Intel Arc B580 2-GPU Optimization Roadmap & Advanced Execution Plan

**Date:** 2026-11-25  
**Target Architecture:** Dual Intel Arc B580 (Battlemage G21, 12GB VRAM each, PCIe 4.0 x8 / x4 asymmetric)  
**Performance Targets:** ~50 tok/s decode, ≥2000 tok/s prefill at 64k context  

---

## 1. Executive Summary & Objective
While standard configuration tuning (`run-strata-2gpu.sh` with 31 high-performance env flags) establishes a stable baseline (~11-15 tok/s decode, ~32-34 tok/s quick prefill, ~1060 tok/s 64k prefill), reaching the ambitious **50 tok/s decode** and **2000+ tok/s prefill** targets requires breaking past hardware and software constraints. 

This roadmap outlines concrete, aggressive engineering directions to achieve maximum performance on 2× B580 without accepting premature hardware ceilings.

---

## 2. Identified Bottlenecks & Architectural Barriers

1. **Asymmetric PCIe Bandwidth (GPU 0 x8 ≈ 16 GB/s, GPU 1 x4 ≈ 8 GB/s):**
   - *Impact:* Stage 1 (GPU 1) must stream over 62% of missing expert weights across an 8 GB/s bus, bottlenecking inter-stage handoffs.
2. **VRAM Residency vs. Expert Cache Tradeoff:**
   - *Impact:* Holding 48 layers of MoE weights (IQ3_XXS) alongside 64k KV cache int8 leaves limited VRAM slots for resident experts (~35.4% residency), forcing continuous host streaming.
3. **TDR Watchdog Limit:**
   - *Impact:* Root-enforced 5-10s `job_timeout_ms` prevents extremely deep kernel pipelining or unyielding prefill batches.
4. **Missing SYCL Tensor Parallelism (TP=2):**
   - *Impact:* Pipeline parallel layer splitting (`PP`) introduces pipeline bubbles and asymmetric bus stress. True tensor parallelism (`TP=2`) with expert-row all-reduce remains unported in the SYCL engine.

---

## 3. Concrete Action Plan & Engineering Directions

### Direction A: Aggressive Prefill Pipelining & Chunk Tuning
- **Mechanism:** Optimize prompt chunking (`PREFILL=16384` or `32000`) combined with pinned host-to-device ring staging (`STRATA_PREFILL_RING=96`, `STRATA_STAGER_RING=16`).
- **Goal:** Maximize prefill throughput toward 1500+ tok/s by saturating both XMX matrix engines without triggering TDR watchdog resets.

### Direction B: Dynamic Expert Cache Re-Allocation & Prefetch Tuning
- **Mechanism:** Tune per-layer expert allocation (`--expert-cache-per-layer`) and aggressive prefetch masks (`STRATA_KV_PREFETCH=1`, `STRATA_IQ_PREFETCH=1`, `STRATA_DISJOINT_ADAPT=1`).
- **Goal:** Increase expert VRAM residency from 35.4% to >45% using tighter quantization (`IQ2_XS` or trimmed stage weights).

### Direction C: Custom Kernel-Level & Scheduler Overrides
- **Mechanism:** Prototype asynchronous stream-splitting and overlapping window sync (`STRATA_WINDOW_SYNC=0`, `STRATA_SPLIT_MISS_MS=108`) to minimize GPU-reach wait times during token decode.
- **Goal:** Push decode throughput from ~12 tok/s toward 25-30 tok/s on 2× B580.

---

## 4. Execution & Verification Workflow
1. **Benchmark Suite:** Run automated multi-case benchmarks (`scripts/measure-quick.py`, `scripts/measure-prefill-decode.py`) under strict coherence gates.
2. **Telemetry Monitoring:** Track Level Zero GPU utilization, VRAM carve allocations, and PCIe bus saturation via `scripts/b580_telemetry.py`.
3. **Persistence:** Update launch scripts and container configurations with proven performance gains.
