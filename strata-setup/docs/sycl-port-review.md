# SYCL port review — B580 work that landed on `main`

_Report dated 2026-10-27 (updated 2026-10-28). Historic in its framing: at the
time no B580 was attached and every milestone below read "hardware-blocked".
Hardware became available later — measured numbers live in `status.md`, not here._

**Refs:** strata-src `main` @ `8eca9d49` (upstream `main` @ `4b9e05a2`);
backup snapshot `perf/2xb580-inference-backup` @ `eebfee1b`.
**Build:** `build-sycl-aot/`, `STRATA_SYCL_AOT=bmg-g21`, `STRATA_XMX_SG16=1`, Release.

AOT correction: `build-sycl-aot` was already `bmg-g21` with XMX sub-group 16.
The earlier claim that AOT was empty and targeting DG2 kernels was wrong; no
rebuild was needed.

## Changes landed (all reviewable without a GPU)

1. **Config fixes** (3 configs): removed `STRATA_WINDOW_SYNC=1`,
   `STRATA_SPIN_MAX=300000`, `STRATA_PREFILL_MMQ=0`, `STRATA_SPLIT_GROUPS=2`.
   The first two suppressed decode; the last was a no-op (default is already 2).
2. **Basalt-derived values** (CUDA-only engine, applied to all 3 configs):
   `--expert-cache 12288` (was `auto`), `--spec 7` (was 4),
   `--vram-reserve-mib 700`. `--peer-exclusive` has no strata CLI equivalent.
3. **`STRATA_SPLIT_GROUPS`** wired in `sycl/src/core/verify.cpp:record_window()`;
   clamped to `min(N, T)`.
4. **`pl_mtp_live[]` reset** + `pl_drain()` indentation fix (CUDA and SYCL
   `generate.cpp`).
5. **SYCL `pl_adapt()`**: thread name/pinning (`aux_cpus.hpp`) + `!ajob` guard,
   matching CUDA.
6. **TP=2 cross-context barrier fixes** — the `verify.cpp:1706` crash. SYCL
   `ext_oneapi_submit_barrier({event})` cannot consume events from another SYCL
   context (CUDA's `cudaStreamWaitEvent` can). Replaced with `event->wait()`
   (host-blocking, context-agnostic) in `generate.cpp` (3 sites) and `verify.cpp`
   (3 sites: `ev_fork_` recorded on `cs` but barrier on `sh_cs_` x2; `ev_join_`
   recorded on `sh_cs_` but barrier on `cs`). Remaining
   `ext_oneapi_submit_barrier` calls (`concurrent_main.cpp`, `graph.cpp`,
   `overlap_main.cpp`, `mtp.cpp`) all use same-queue events — unaffected.
7. **#879 non-finite logit guard** ported: `logits_nonfinite_rows` kernel in
   `verify_kernels.dp.cpp`; `note_nonfinite()` in `run()`, `run_slot_rows()`,
   `batch_poll()`, `pl_finish()`; `STRATA_NAN_GUARD` (default on),
   `STRATA_NAN_INJECT` test hook.
8. **`STRATA_SPLIT_OVERLAP=1` port**: kernels `wait_handoff`/`handoff_publish`,
   statics `g_split_wait_ns` / `g_test_drop`, host-USM hand-off flags, wiring in
   `generate.cpp`, `handoff_failed()` check in `run()`, `prelaunch()` /
   `NextLaunch` helper-thread chain path. **Race fixed**: `run()` called
   `next_->run()` without joining `NextLaunch` — added `nl.join(err);
   nl.handed = true;` before it (matches CUDA `verify.cpp:3101-3105`).
   `n_stages >= 2` pipelining was already generic, not hardcoded to 2.
9. **Adapt-async offload infra** (`a_pl_idle`, `a_gap_seq`, `ahomes`,
   `a_back()`/`a_in()` at gaps, `a_ready()`/`a_flush()`, `adapt_tick()` with gap
   gating), ported from CUDA `src/program/generate.cpp:10591-10593`.
10. **Build fixes**: `fence_space::local_and_global` -> `local_space`;
    `sycl::atomic_ref<volatile>` -> `dpct::atomic_fetch_add<const_cast>()`.

## Verification state

- `ninja strata_engine`: 120/120 clean.
- Python tools suite: 1264 passed, 5 failed (pre-existing, reproduced on pristine
  `4b9e05a2`), 3 skipped, 585 subtests passed.
- C++ ctest: 26/38 pass; 12 fail on environment only (no GPU OpenCL backend, no
  oneMKL) — pre-existing.
- Full `ninja` fails on `strata_prefill` (missing oneMKL headers) — pre-existing.
- `scripts/measure-baseline.sh` added (validate/build/parity/protocol/env-check/xpu).

## Basalt patterns — algorithmic, not portable

Basalt is CUDA-only on NVIDIA Blackwell (sm_120); zero SYCL/XMX/oneAPI in source.
Patterns worth borrowing later: expert cache (no-eviction default, heat+prior+index
ranking, adaptive swaps with decay), staged copy (4-buffer ring, O_DIRECT 16 MiB
chunks), router cost model (gain/cold-victim swap heuristic), decode loop
(one-layer-delay overlap, doorbell polling). Not applicable: int8 fused
dequant-into-scratch KV cache (strata uses GGUF K-quant).

## SYCL vs CUDA divergences worth tracking

| Area | CUDA | SYCL | Impact |
|---|---|---|---|
| AOT target | n/a | `bmg-g21` + `STRATA_XMX_SG16=1` | correct for B580 |
| adapt-async offload | `ahomes`, `a_pl_idle`, `a_gap_seq` | ported | `--adapt-async 1` works |
| pipelined windows | `n_stages >= 2` | ported | generic N-stage splits |
| chain_overlap | `NextLaunch` + `prelaunch()` | ported, join race fixed | overlapped split enabled |
| MTP dispatch | ~5 us/kernel | 100-500 us/kernel | known SYCL limitation (llama.cpp #23533) |

## Community references

| Source | Finding |
|---|---|
| llama.cpp #25025 | oneMKL GEMM flash attention for XMX on Battlemage: PP ~671 tok/s @ 32K, ~335 @ 110K |
| Sergio B. (B70) cookbook | `q8_0` K + `q4_1` V; MTP-4 gave 21.3 -> 29.75 tok/s |
| jonathanmann.tech (B70) | SYCL f16 KV cache stable at 32K vs quantized decay |
| B70 high-concurrency | `-b 8192 -ub 4096 --parallel 32` micro-batching |

Baseline references from prior measurements: 1-GPU old env ~10.5-13 tok/s; 2-GPU
old env ~37-43 tok/s. B70 reference (not B580): Coder IQ1_M at 78.2 tok/s greedy
on Strata SYCL, 66.6 at 128K.