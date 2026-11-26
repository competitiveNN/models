# Next Optimization Plan — Dual B580 Strata (Post-Ceiling Audit)

**Date:** 2026-11-26  
**Scope:** Concrete, evidence-grounded improvements after the 2× Intel Arc B580 ceiling audit.  
**Hardware ceiling (confirmed):** no Level-Zero P2P, asymmetric PCIe x8/x4, 12 GB/GPU, ~35.4% expert residency, TDR 5000 ms. TP=2 not viable in current SYCL engine.

## Targets and measured baseline

| Metric | Target | Measured (best verified) | Gap | Bound |
|---|---:|---:|---:|---|
| Single-stream decode | ≥50 tok/s | ~15.5 tok/s (kernel-fused-max), 24.3 tok/s (regression audit snapshot) | 2.1–3.2× | PCIe expert streaming / residency |
| 64k prefill | ≥2000 tok/s | ~1000 tok/s | 2.0× | PCIe x4 stage transfer / prompt staging |
| Aggregate decode (`--parallel 8`) | maximize | ~119 tok/s | n/a | slot packing, not single-stream |

Single-stream targets remain **hardware-bounded** on 2× B580 PP=2. Improvements below focus on reducing avoidable overhead, improving observability, and making regression/launch behavior explicit and reproducible.

## Evidence anchors

- `docs/B580_CEILING_AUDIT.md` — PCIe/TDR/P2P/residency limits; verified/no-op flags.
- `docs/FORK_PORTS.md` — fork portability; TP=2 not portable; split overlap regressed.
- `runs/regression_audit_report.json` — strict SLA gate, exit 2 on unmet targets.
- `runs/kernel-pipeline-verification.md` — kernel-fused-max profile: 15.5 tok/s decode, 999.3 tok/s 64k prefill.
- `run-strata-2gpu.sh` — env-tunable launch path; default ring/staging values.
- `configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json` — aggressive ring/staging/profile reference.

## Planned improvements (execute now)

### 1) Advanced async ring-buffer / DMA staging profile wiring
**Problem:** Kernel-fused-max config uses aggressive ring/staging/env values (`STRATA_PREFILL_RING=1024`, `STRATA_STAGER_RING=256`, `STRATA_PCIE_SPLIT_MODE=asymmetric`, `STRATA_MOE_DMA_OVERLAP=1`, `STRATA_ASYNC_RING_BUFFER=1`, `STRATA_POOL_SPIN_US=100`) that are not first-class in `run-strata-2gpu.sh`.  
**Action:** Add env-tunable wiring for missing profile env vars in `run-strata-2gpu.sh`, add a `--kernel-fused-max` mode with evidence-backed defaults, and keep all values overridable via env.  
**Value:** Reproducible high-throughput staging profile; avoids manual env drift.  
**Risk:** Larger rings increase host RAM/VRAM pressure; keep defaults conservative outside profile mode.

### 2) Telemetry hardening for PCIe/NUMA/TDR observability
**Problem:** `scripts/b580_advanced_telemetry.py` captures only basic health/lspci/sycl-ls; it does not expose sysfs PCIe link width/speed, TDR/job_timeout, render-node topology, NUMA, or CPU affinity.  
**Action:** Extend telemetry to collect structured sysfs PCIe/TDR/NUMA/CPU data, include command provenance and warnings, and keep graceful degradation when tools/files are unavailable.  
**Value:** Makes bottleneck diagnosis and regression triage evidence-based; supports async DMA/pipelining experiments.  
**Risk:** Low; read-only collection.

### 3) Strict SLA regression audit enrichment
**Problem:** `scripts/strata_regression_audit.py` has hardcoded URL/output/targets and limited metadata; hard to compare runs or integrate in CI.  
**Action:** Add CLI args (`--url`, `--output`, `--decode-target`, `--prefill-target`, `--timeout-*`, `--prompt-chars`), capture git SHA/host/platform/config metadata, include coherence smoke, and preserve exit-code semantics (0 pass, 2 target miss, 1 execution error).  
**Value:** Repeatable, machine-readable gating; clearer hardware-ceiling reporting.  
**Risk:** Low; backward-compatible defaults.

### 4) Documentation reconciliation
**Problem:** `docs/ADVANCED_B580_BYPASSES.md` lists flags as bypasses without binary verification status; can be misread as active engine features.  
**Action:** Add verification status column/notes grounded in `docs/B580_CEILING_AUDIT.md` and fork-port evidence; mark unverified/no-op flags explicitly.  
**Value:** Prevents wasted tuning cycles on no-op flags.  
**Risk:** None.

### 5) Script/config validation tests
**Problem:** New/changed Python scripts have no fast sanity tests.  
**Action:** Add lightweight pytest tests that mock network/subprocess/file reads for telemetry and regression audit; validate JSON configs touched.  
**Value:** Guards against regressions in observability/gating tooling.  
**Risk:** Low; tests must not require live server/GPU.

## Future work (not executable without engine/source changes)

| Candidate | Expected impact | Blocker | Next evidence needed |
|---|---|---|---|
| True async DMA + compute overlap in SYCL engine | Medium for prefill, low-medium for decode | Requires engine/kernel changes in strata SYCL source; many flags not in binary | Binary flag audit + profiler traces showing DMA/compute overlap gaps |
| PCIe-aware expert placement / hot-expert pinning | Medium | Needs residency telemetry per expert and engine support | Per-expert hit/miss counters, VRAM residency map |
| Host-staged pseudo-TP / AllReduce shim | Low/negative likely | No P2P; x4 link latency; no SYCL AllReduce primitive | Microbenchmark host-staged reduce over x4/x8 |
| Draft 2-bit bit-planes / pinned prompt reads | Low-medium | Fork features not ported to SYCL engine | Port feasibility in `strata-src` SYCL paths |
| 4× B580 / PCIe 5.0 x16 / NVLink / larger VRAM | High | Hardware procurement/topology | Cost/perf model |

## Exit criteria for this pass

- [x] Plan documented with evidence and blockers.
- [ ] `run-strata-2gpu.sh` exposes kernel-fused-max/async-staging env wiring.
- [ ] Telemetry script captures PCIe/TDR/NUMA/CPU structured data.
- [ ] Regression audit script supports CLI + richer metadata while preserving gate semantics.
- [ ] Docs reconciled for no-op/unverified flags.
- [ ] Python syntax/tests pass for touched scripts.
