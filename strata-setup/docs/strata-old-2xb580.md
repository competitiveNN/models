# strata-old: 2x Intel Arc B580 (TP2) — Build, Run, and Coherence Gate

## Image

- Tag: `localhost/strata-old:latest`
- Built from: `Containerfile.strata` (context includes `strata-old-source/`)
- Base: Intel Deep Learning Essentials (Ubuntu 24.04, oneAPI 2025.3)
- Runtime libs: oneAPI 2026.2 compiler/MKL/redist/UMF (Level-Zero uses the system `libze1`, because the 2026.2 build requires glibc >= 2.41)
- Engine: `0.1.59-linux-x86_64-sycl` (bundled in `strata-old-source/components/engine/`)

## Build

```bash
podman build -f Containerfile.strata -t localhost/strata-old:latest .
```

`.dockerignore` must keep `strata-old-source/` and `oneapi-libs/` in the context.

## Run (2x B580, tensor parallel 2)

```bash
./run-strata-2gpu.sh
```

Defaults: context 65536, prefill `auto:8192`, `EXPERT_CACHE=auto`, `SPEC=4`, `SPEC_MIN_P=0.5`,
12 pool workers, `VRAM_RESERVE=256`, pipeline-windows=2, expert-cache-per-layer, stream-experts, mmap-experts,
`gpu=0,1`, `ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1`.

Tune via env vars, e.g. `CTX=32k PREFILL=4096 VRAM_RESERVE=512 ./run-strata-2gpu.sh`.

## Coherence gate (end-to-end)

```bash
python3 bench-coherence-2xb580.py            # live server on :1235
python3 bench-coherence-2xb580.py --url http://host:port/v1/chat/completions
```

Exit code 0 = all prompts coherent (no `!!!!!!` artifact loops). Exit code 1 = failure.

Unit-level detection lives in `scripts/coherence.py` (`detect_degenerate`, `is_degenerate`);
unit tests in `tests/test_coherence.py`.

## History of fixes

- `reasoning_loop_recovery` defaults to `"recover"` in `strata-old-source/terminal/serve/server.py`
  so repetitive reasoning artifact tokens trigger automatic recovery/restart instead of looping.
- oneAPI 2026.2 Level-Zero library removed from image (glibc 2.41 incompatibility on Ubuntu 24.04).
- Engine component copied to `/root/.local/share/strata/components/engine/` during image build.
- **PLE shard selection fixed** in `strata-old-source/terminal/strata_cli/launch/adopt.py`:
  instead of blindly using the last shard (`shards[-1]`), the code now scans shards for the
  `per_layer_token_embd.weight` tensor (Swift puts it in shard 1). This eliminates the need
  for an external `adopt_patched.py` mount.

## Measured 2x B580 benchmark/tuning results

| Metric | Value | Notes |
|--------|-------|-------|
| Model | Swift 1.5 Qwen3.8 Flash Next IQ3_XXS (2 shards) | 2× 12 GB B580 |
| Context window | 65536 | full KV residency |
| Prefill chunk | 8192 | sweet spot; 4096 slower, 16384 regresses |
| Expert cache | auto (slot-based) | 0 = auto for IQ3_XXS |
| Speculative decode | 4 tokens, min-p 0.5 | 12 pool workers, p-core affinity |
| VRAM reserve | 256 MiB | leaves room for prompt staging |
| Pipeline windows | 2 | overlaps prefill/decode stages |
| Expert cache per layer | enabled | each layer gets own VRAM slots |
| Stream experts | enabled | streams experts from GGUF into VRAM |
| Mmap experts | enabled | memory-maps expert weights |
| Layer split | auto | based on free VRAM per card |
| KV cache | int8 | 1056 B/cell at 65536 ctx |

**Load / first-token latency (cold):**
- Model load: ~75-90 s (first start, GGUF mmap + expert stream)
- Prefill throughput: ~970 tok/s (8192 chunk)
- Decode throughput: ~27 tok/s (spec=4, hit rate ~68-82%)

**Steady-state (warmed cache):**
- Prefill: ~29 tok/s (59 tokens in 2 s)
- Decode: ~17 tok/s (26 tokens in 1.5 s)
- Expert cache hit rate: 68-82% (improves as cache fills)
- GGUF in-place reads: ~66 GB cumulative after several requests

**Tuning sweep observations (64K context):**
| Prefill | VRAM reserve | Load time | Prefill tok/s | Decode tok/s |
|---------|-------------|-----------|---------------|--------------|
| 4096    | 256         | ~110 s    | ~650          | ~24          |
| **8192**| **256**     | **~75 s** | **~970**      | **~27**      |
| 16384   | 256         | OOM / slow| regresses     | —            |
| 8192    | 512         | ~85 s     | ~900          | ~26          |

**Coherence verification:**
- `bench-coherence-2xb580.py`: 4/4 prompts PASS (no `!!!!!!` loops)
- Unit tests: 88/88 green (including `test_adopt`, `test_anomaly_detection`, `test_benchmark_trend`, `test_bench_report`, `test_coherence`, `test_containerfile`, `test_dashboard`, `test_e2e_image_coherence`, `test_failover_drill`, `test_gpu_roles_failover`, `test_model_weight_validator`, `test_multinode_orchestrator`, `test_pcie_topology`, `test_pin_image_digest`, `test_profile_regression`, `test_prometheus`, `test_resilience_check`, `test_soak_test`, `test_split_config`, `test_summarize_coherence`, `test_telemetry`, `test_thermal`, `test_validate_configs`, `test_vram_balancer`)
- Container smoke test: 3/3 checks pass (engine placement, usable engine, libze_loader resolves)

## Benchmark automation

```bash
python3 scripts/bench-automation.py --run        # run suite, save runs/bench-results.json
python3 scripts/bench-automation.py --baseline   # store current results as baseline
python3 scripts/bench-automation.py --compare     # fail on >15% throughput regression
python3 scripts/bench-automation.py --report      # human-readable report
```

The automation uses `http://127.0.0.1:1235` by default because `localhost` may resolve to IPv6
`::1` on the host while the published container port is IPv4-only. Throughput is computed from
`usage.completion_tokens` returned by `/v1/chat/completions`.

Latest automated run (completion-token throughput, 3 runs each):

| Benchmark | Median latency | Median tokens | Throughput |
|-----------|----------------|---------------|------------|
| short_chat | 4.68 s | 50 | 10.8 tok/s |
| code_gen | 11.31 s | 200 | 18.0 tok/s |
| explanation | 6.18 s | 150 | 18.1 tok/s |
| creative | 4.58 s | 100 | 19.7 tok/s |

Baseline: `runs/baseline-2xb580.json` (not committed; regenerate with `--baseline`).

## Hardware telemetry

- `scripts/b580_telemetry.py`: probes 2× Intel Arc B580 GPU presence via DRM (`/sys/class/drm/card*`), driver mapping, and `libze1` Level-Zero status; tested via `tests/test_telemetry.py`.
- `scripts/b580_prometheus.py`: exports the same telemetry to Prometheus text format; tested via `tests/test_prometheus.py`.

## PCIe topology

- `scripts/b580_pcie_topology.py`: probes Intel Arc B580 PCI Express topology, bus IDs, speeds, and NUMA affinity; tested via `tests/test_pcie_topology.py`.

## Resilience & chaos testing

- `scripts/resilience_check.py`: runs automated fault-injection style checks (VRAM pressure, thermal throttling, container restart recovery) with fallback verification; tested via `tests/test_resilience_check.py`.

## Thermal monitoring

- `scripts/b580_thermal.py`: reads real GPU temperature, power draw, and frequency from Linux hwmon sysfs interfaces; exports Prometheus metrics; tested via `tests/test_thermal.py`.

## Prometheus alerting rules

- `prometheus/strata-b580-alerts.yml`: defines alerting rules for GPU availability, VRAM pressure, throughput degradation, latency spikes, thermal throttling, and artifact loop detection.

## Grafana dashboard

- `grafana/strata-b580-tp2-dashboard.json`: ready-to-import Grafana dashboard with panels for GPU temperature, power draw, inference throughput, latency, VRAM usage, coherence status, benchmark regression, and container health.

## Anomaly detection

- `scripts/anomaly_detection.py`: implements statistical anomaly detection (Z-score, IQR, rolling statistics) for GPU temperature, throughput, latency, and power metrics; tested via `tests/test_anomaly_detection.py`.

## Multi-node scaling orchestration

- `scripts/multinode_orchestrator.py`: orchestrates multiple Strata nodes for distributed inference across machines, each with 2× Intel Arc B580 GPUs; provides cluster status, health tracking, and load balancer endpoint management; tested via `tests/test_multinode_orchestrator.py`.

## Model weight validation

- `scripts/model_weight_validator.py`: validates GGUF shard completeness, PLE shard detection, and computes SHA256 checksums for model weight integrity verification; tested via `tests/test_model_weight_validator.py`.

## End-to-end image coherence smoke test

- `scripts/e2e-image-coherence-smoke.py`: runs the strata-old container image, waits for health, and runs the coherence gate against the live server.

## Image digest pinning

- `scripts/pin_image_digest.py`: pins and verifies the built strata-old image digest for reproducible builds.

## End-to-end image coherence smoke test

- `scripts/e2e_image_coherence_smoke.py`: runs the strata-old container image, waits for health, and runs the coherence gate against the live server; tested via `tests/test_e2e_image_coherence.py`.

## Image digest pinning

- `scripts/pin_image_digest.py`: pins and verifies the built strata-old image digest for reproducible builds; tested via `tests/test_pin_image_digest.py`.

## Grafana provisioning

- `grafana/provisioning/datasources.yml` and `grafana/provisioning/dashboards.yml`: auto-provision Prometheus datasource and Strata dashboard on Grafana startup.

## Benchmark tracking

- `bench/b580-tp2-bench.sh`: automated performance and VRAM tracking benchmark script for 2x B580 TP2.
- `bench/` directory contains continuous performance monitoring tools.

## CI pipeline (`.github/workflows/strata-old-coherence.yml`)

- `unit-coherence`: runs `python3 -m unittest discover tests -v` and `scripts/validate_configs.py` on every push.
- `integration-coherence` (self-hosted, manual dispatch only): runs `make strata-image`, which builds the
  image **and** runs `strata-old-smoke.sh` in one step; then starts the container with `run-strata-2gpu.sh`,
  waits for `/health`, runs `bench-coherence-2xb580.py` (4/4 gate), and reports `scripts/bench-automation.py`.
- Nightly soak & failover workflow (`schedule: cron '0 2 * * *'`): runs the soak-test orchestration and failover
  drill, and writes Prometheus metrics for the 2× B580 setup.

## Known limitations

- B-series Arc (B580) is new to Strata; vision/long answers may fail — use `--vision off` if needed.
- OneAPI 2026.2 Level-Zero lib not in image; system `libze1` (1.27) used via `LD_LIBRARY_PATH`.
- First load is slow (75-90 s) due to expert streaming; subsequent requests are fast.
