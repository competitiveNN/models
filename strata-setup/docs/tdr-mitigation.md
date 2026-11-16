# TDR mitigation and 2-GPU hand-off — plan

_Status 2026-11-15. Measured on the dual Arc B580 rig (Xe driver) with
`build-sycl-aot/strata`._

## Constraint

The GPU job timeout is `job_timeout_ms = 5000` (both cards,
`.../tile0/gt0/engines/{ccs,rcs}/`). `job_timeout_max = 10000`, so even a root
change caps at 10 s — still below the multi-second split windows. Sysfs is
`root:root`; the run user `fra` is in `wheel` but has no NOPASSWD, and
`--privileged`/`--userns=host` do not help (verified: write -> Permission denied).
**Every GPU submission must therefore finish in < 5 s.**

## What works / what does not

Measured this session:

| Configuration | Result |
|---|---|
| 1 GPU, stepped, cache 64, prefill 1 | READY; 8.0 tok/s (cold first request) |
| 1 GPU, stepped, cache 3072, prefill 8/32/128 | READY; 9.5 tok/s cold, **14.4-14.6 tok/s warm median** |
| 1 GPU, single verifier (no split), stepped, cache 3072 | DEVICE_LOST (one 48-layer window > 5 s) |
| 1 GPU, single stage, no stepped, cache 3072 | DEVICE_LOST, 503 after 84 s |
| 2 GPU layer split (serial or stepped), any cache | DEADLOCK at layer-27 hand-off, 60 s stall |
| 2 GPU layer split + `STRATA_SPLIT_OVERLAP=1` | Kernel error: non-uniform work-groups unsupported (`verify.cpp:2883`) |

Root-cause chain for the 2-GPU failure:

1. Stage 0 (CUDA0, layers 0-26) finishes; stage 1 (CUDA1, 27-47) never starts
   (`0 layers served`, "GPU rang 27" then nothing).
2. The DEVICE_LOST is raised at the **pre-launch** window sync (`verify.cpp:2344`)
   while the previous window's stage-1 work is still in flight.
3. `queue_wait_diag()` (`verify.cpp:2650`) polls `ext_oneapi_empty()` and
   **returns success after its budget even if the queue is not empty** (by
   design, to avoid poisoning the B580 queue). The next window's hard
   `queues_wait_and_throw()` then blocks on that stale work and trips the TDR.
4. The try/catch at `:2344` **swallowed** the DEVICE_LOST, so execution continued
   on a lost device until the 60 s stall watchdog killed the engine.

Cross-stage hand-off is a host-USM buffer written by CUDA0 and read by CUDA1. The
Xe driver does not make host<->GPU flag stores reliably visible while a graph runs
(`sycl_doorbell.hpp`; `STRATA_VERIFY_NO_HOST` exists for this reason), which
matches "GPU rang 27 then nothing".

## P0 — automated TDR-safe configuration (done)

`scripts/tdr_safe_config.py` probes GPUs/VRAM (`xpu-smi`), sizes `--expert-cache`
to fill free VRAM after weights (fewer streamed experts -> shorter windows),
selects a TDR-safe `--prefill` chunk, forces `STRATA_VERIFY_STEPPED=1` on 1 GPU,
and refuses to emit a 2-GPU split config (documents the blocker, exit 3).
Validated end-to-end via `scripts/battery_cfg.py`: boots, serves, 14.4 tok/s warm.

Known-good 1-GPU baseline (intra-GPU layer split, stepped, large cache):

```
--layer-split 47 --split-device 0 --expert-cache 3072 --prefill 32 --spec 2 \
--kv q4_0 --vram-reserve-mib 1024 --pipeline-windows 0
env: STRATA_VERIFY_STEPPED=1 STRATA_VERIFY_NO_HOST=0 STRATA_WINDOW_SYNC=1 \
     ZE_FLAT_DEVICE_MEMORY=1 ONEAPI_DEVICE_SELECTOR=level_zero:0
```

Stepped mode and the split are both **mandatory**: without them a single 48-layer
window exceeds 5 s and TDRs.

## P1 — clean DEVICE_LOST abort (done)

At the pre-launch window sync (`verify.cpp:2344`) treat DEVICE_LOST as a fatal
window error: set `err` and return false so the engine restarts cleanly instead
of hanging 60 s. Validated: a 2-GPU request that previously hung now returns
HTTP 503 in 9.6 s. Reliability win, not a TDR fix.

## P2 — honest window sync

Replace the "poll then return success" contract of `queue_wait_diag` with a
completion check driven by the doorbell ring (the actual completion signal) rather
than `ext_oneapi_empty()`. Removes the class of bug where the next hard wait
blocks on already-abandoned work.

## P3 — cross-device hand-off visibility (the real 2-GPU fix)

Make CUDA0's hand-off writes coherent/visible to CUDA1 before stage 1 reads them
(uncached/sys-scope stores + an explicit device barrier between stages), and ring
a per-stage doorbell the host actually observes. Highest-value item.

## P4 — port SPLIT_OVERLAP kernels to uniform work-groups

`wait_handoff`/`handoff_publish` are rejected on B580 at launch; required before
the overlap path can be used.

## P5 — adaptive prefill chunking

Start at a moderate chunk, measure wall time, shrink when it nears the budget
(e.g. 3.5 s). Lets prefill run as fast as the TDR allows; the path toward
1400 tok/s (see `prefill-ceiling.md`).

## Alternatives that bypass the whole class of bugs

| Option | Result |
|---|---|
| Raise `job_timeout_ms` to 30000 (root) | 2-GPU split should run without mitigations |
| Alchemist A750/A770 (i915) | TDR configurable; full validation possible |
| Windows + B580 | Registry `TdrDelay`; full validation possible |
| Reduce verify window layers + aggressive sync (`STRATA_VERIFY_CHUNK_LAYERS`) | Tested 2..24 layers: 30 s timeout, no improvement |
| Small expert cache (`--expert-cache 64`) | Still DEVICE_LOST / timeout |
| Clean config, no mitigations | DEVICE_LOST at ~5 s |

## Benchmark methodology (keep results comparable)

- Warm page cache and expert working set before timing: cold first request is
  ~2x slower (8 vs 14.6 tok/s here).
- Report medians over >= 6 requests from one server session
  (`scripts/battery_cfg.py`).
- Record the engine log (`VRAM free`, `expert cache slots`, `missing from VRAM`)
  with every number — cache size moves throughput more than any other knob.
- Never compare cold vs warm, or cross-day numbers (page-cache state drifts).

## Open questions

1. Does P3 alone make the serial 2-GPU split serve? Needs a rebuild.
2. With P3 fixed, does P0 cache sizing push the split toward ~40 tok/s?
3. How close can 1-GPU prefill get to 1400 tok/s with P5 chunking?