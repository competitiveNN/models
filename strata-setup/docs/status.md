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