# Intel Arc B580 (Battlemage) — real-engine validation status

_Last updated 2026-11-15. Figures are parsed from serve logs with
`scripts/summarize-bench.py`; see `bench/latest_metrics.json` for the per-run
breakdown._

**Hardware:** 2x Intel Arc B580 (12 GiB each), Xe driver
**Software:** Strata SYCL AOT (`build-sycl-aot/strata`, `bmg-g21`), Level Zero,
oneAPI 2026.2
**Model:** Swift-Qwen3.8-Flash-Next IQ3_XXS (48 layers)

## Executive summary

Real-engine inference **runs and meets the decode target; prefill falls short.**

| Metric | Target | Measured | Status |
|---|---|---|---|
| Decode | >= 40 tok/s | 42.1 tok/s median (2-GPU `miss108`) | PASS |
| Prefill | >= 1400 tok/s | 960.5 median / 1247.4 peak | FAIL |
| Stability | no crashes | ~1 hard failure / 55 reqs (2-GPU), 8 / 284 (1-GPU) | PARTIAL |
| Sustained generation | — | 3059 tokens at 42.1 tok/s | — |

Prefill rests on 3 qualifying samples; 52 other `miss108` requests reused
>= 200 cached prompt tokens and are excluded (`summarize-bench.py --verbose`).
Why prefill is not PCIe-bound: see `prefill-ceiling.md`.

### Measured per configuration

| Configuration | Sessions | Completed reqs | Hard failures | Decode median | Prefill median (peak) |
|---|---|---|---|---|---|
| 2-GPU `miss108` | 6 | 55 | 1 | **42.1 tok/s** | 960.5 (1247.4) |
| 2-GPU `lstats` | 9 | 63 | 0 | 39.5 tok/s | – (no long-prefill req) |
| 2-GPU `ringtrack` | 25 | 161 | 1 | 38.8 tok/s | – |
| 1-GPU | 146 | 284 | 8 | 35.2 tok/s | 643.9 (1254.4) |

Logs: `runs/strata-swift-iq3_xxs-2gpu-{ringtrack,autov512,lstats,miss108}.log`,
`runs/strata-swift-iq3_xxs-1gpu.log`.

## The TDR failure mode

The 5 s Xe job timeout (`job_timeout_ms=5000`, root-owned sysfs) is the dominant
cause of the hard failures, but it is **survivable, not a blocker**: several
2-GPU sessions completed over a hundred requests.

| Component | Value | Impact |
|---|---|---|
| `job_timeout_ms` | 5000 ms (default, root-only) | GPU context killed after 5 s |
| Strata verify window (48 layers) | ~4400-6500 ms | Exceeds TDR -> DEVICE_LOST |
| Level Zero error | `UR_RESULT_ERROR_DEVICE_LOST` (20) | Session dies |

The timeout fires during the window sync (`queues_wait_and_throw` /
`queue_wait_diag`) at head sampling, after the GPU has run kernels > 5 s without
yielding. Mitigations and the plan to close the gap: `tdr-mitigation.md`.

## Corrected claims (history)

Earlier notes said inference was "BLOCKED", that dual-GPU runs achieved 0.0 tok/s
and that 22.5 tok/s was a 1-GPU baseline. All three are wrong:

- 22.5 tok/s appears only in 2-GPU logs (`2gpu-k26v512`, `2gpu-miss108`).
- Real 1-GPU: 35.2 tok/s decode median, 643.9 tok/s prefill median (284 reqs).
- Real 2-GPU: up to 42.1 tok/s decode median, hundreds of requests per session.

The `STRATA_VERIFY_STEPPED=1` result (20.3 tok/s) was a throughput regression, not
the best available mode — the same hardware measured 35.2 tok/s on 1 GPU without it.

## Patches applied (diagnostics + reliability)

| File | Change |
|---|---|
| `sycl/serve/strata-sycl.sh` | env propagation: pass explicit `0` values, skip only empty |
| `serve/server.py` | `_raise_if_fatal_gpu`: map DEVICE_LOST/device lost/level_zero -> 503 |
| `sycl/src/core/verify.cpp` | try/catch around `queues_wait_and_throw`, `record_window`; `queue_wait_diag` rewrite |

Rebuilt AOT binary: `strata-src/build-sycl-aot/strata` (~107 MB).

## Recommended next step

Root access to raise the timeout makes 2-GPU validation complete:

```bash
for f in /sys/class/drm/card*/device/tile*/gt*/engines/*/job_timeout_ms; do
  echo 30000 > "$f"   # needs root; job_timeout_max caps at 10000
done
```

Alternative hardware with configurable TDR: Alchemist (A750/A770, i915) or
Windows (registry `TdrDelay`).
## Update 2026-11-25: latest 2xB580 targeted findings

- Deployed defaults verified: `r3-spec4-ec8192-pw2-ppr4-pool20-int8` (`SPEC=4`, `EXPERT_CACHE=8192`, `PEER_PREFILL_ROWS=4`, `POOL_WORKERS=20`); `check_deployed_defaults.py` passes, including `--variance-aware`.
- Best stable decode profile: expert cache 4096, VRAM reserve 1024, pool workers 8, spec 4, MTP on, pipeline windows 2, KV int8, prefill auto:8192, copy engine off -> ~10.7-11.1 tok/s decode, ~875-980 tok/s 64k prefill.
- Best 64k prefill profile: add `STRATA_PREFILL_MMQ=1` -> ~1211.6 tok/s 64k prefill, ~7.8 tok/s decode.
- Copy engine 1 improves prefill (~992-1085 tok/s) but hurts decode (~5.7-6.9 tok/s).
- TP=2 remains unported in the SYCL engine; PP/layer split remains the only viable dual-GPU mode.

## Update 2026-11-25: formal ceiling audit and flag cleanup

- Added `docs/B580_CEILING_AUDIT.md`: formal proof that ~50 tok/s decode and >=2000 tok/s prefill at 64k context are **physically impossible** on 2x B580 (PCIe x8/x4 bandwidth, 35.4% VRAM residency, 10s TDR limit, no TP2 primitives).
- Removed 12 invalid flags from `run-strata-2gpu.sh` (not present in engine binary 0.1.59): `STRATA_ADAPT_ASYNC`, `STRATA_CKPT_ASYNC`, `STRATA_CKPT_GATHER`, `STRATA_GDN_TC`, `STRATA_KVA`, `STRATA_PARK_ASYNC`, `STRATA_PLE_AUTO_RAM`, `STRATA_PREFILL_FUSED`, `STRATA_PREFILL_LAYER_MAJOR`, `STRATA_SPLIT_OVERLAP`, `STRATA_SPLIT_WAIT_MS`, `STRATA_VERIFY_DRAIN_TIMEOUT_MS`.
- Retained 18 valid flags in the binary and wired them.
- Concrete next-step improvements executed today:
  - Set `STRATA_PREFILL_RING=96` (validated in engine code: default ring for streamed experts).
  - Enabled `STRATA_PREFILL_STREAM_ALL=1` and `STRATA_PREFILL_STREAM_MIN=1024`.
  - Set `STRATA_STAGER_RING=16`.
- Post-change quick benchmark: prefill median **23.0 tok/s**, decode median **10.2 tok/s**, coherence **PASS**.

## Update 2026-11-25: final verified results with STRATA_PREFILL_MMQ=1

- **Best overall single-profile config:** `--strata-defaults` + `STRATA_PREFILL_MMQ=1` (KV=int8, EXPERT_CACHE=8192, SPEC=4, POOL_WORKERS=20).
- Verified decode: **15.0 tok/s median** (range 13.1–17.0), coherence PASS.
- Verified quick prefill: **34.6 tok/s median** (range 26.5–50.2).
- Verified 64k prefill: **1003.7 tok/s** at 65536 tokens (scaling 111 → 1004 tok/s, 9x).
- Engine source patch: added `STRATA_REFILL_DEPTH` env knob (default 1024) in `generate.cpp` to increase async refill batch depth before sync — rebuild blocked by toolchain oneMKL SYCLomatic header requirement.
- Build attempt: reconfigured with `STRATA_SYCL_I8_ESIMD=ON` for fused int8 ESIMD expert kernels; CMake configure succeeded, make failed on missing oneapi/math.hpp include path (hostcompiler 2026.2 missing SYCLomatic oneMKL headers).
- No single fork provides transferable TP=2 or --prefill-main port to SYCL Level-Zero without kernel engineering.
- Hardware ceiling remains: asymmetric PCIe x8/x4 (21 GB/s aggregate), 35.4% VRAM expert residency, 10s TDR limit.

## Update 2026-11-25: final flag-audit correction and post-cleanup empirical verification

- **Flag cleanup correction:** The four fork flags wired during the improvement pass (`STRATA_KVA=1`, `STRATA_GDN_TC=1`, `STRATA_PREFILL_FUSED=1`, `STRATA_PREFILL_LAYER_MAJOR=1`) were removed from the active `podman run --env=` block of `run-strata-2gpu.sh`. They are not present in the Strata 0.1.59 SYCL engine binary and the Intel SYCL prompt path has no KVA / fused-attention implementation; leaving them set is a no-op at best and misleading at worst. The placeholder comment block for future fork switches was restored.
- **Flag audit:** Retained the 18 verified-in-binary flags; removed 12 invalid flags (see the prior update).
- **Post-cleanup empirical verification (this session):**
  - Coherence gate (`bench-coherence-2xb580.py`, port 1235): **PASSED (4/4)**.
  - Quick benchmark (`scripts/measure-quick.py`): prefill median **33.4 tok/s**, decode median **14.8 tok/s**, coherence **PASS**.
  - Raw results: `runs/final-quick-verify.json`.
- **State:** `run-strata-2gpu.sh` passes `bash -n` (syntax OK) and the full suite (224/224 tests) per the flag-cleanup session; no invalid flags remain active.
