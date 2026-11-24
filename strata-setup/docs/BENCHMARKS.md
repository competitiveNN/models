# Strata Benchmark Automation Suite

## Overview

The Strata benchmark automation suite provides end-to-end performance validation,
regression detection, trend reporting, and observability exports for the Strata
SYCL inference engine on dual Intel Arc B580 (Battlemage) GPUs.

## Components

| Component | File | Purpose |
|---|---|---|
| Multi-image benchmarks | `scripts/bench-containers.py` | Runs comparable benchmarks across `ghcr`, `old`, and `edge` containers |
| Stress/Concurrency testing | `scripts/stress-test.py` | Concurrent load testing with degeneracy detection |
| Trend & Regression Report | `scripts/bench-report.py` | Aggregates `runs/*.json` into Markdown + JSON + Prometheus reports |
| Unit Tests | `tests/test_bench_report.py` | Unit tests for report parsing, quantiles, histograms, moving averages, IQR anomaly detection, Prometheus formatting |
| CI Wrapper | `scripts/run-benchmarks.sh` | Atomic local/CI execution (unit tests + report generation + regression gate) |
| GitHub Actions | `.github/workflows/benchmarks.yml` | Push/PR/workflow_dispatch CI: tests, report generation, artifact upload |
| Makefile | `Makefile` | `make test-bench`, `make bench-report`, `make test-all` targets |
| Pre-commit hooks | `.pre-commit-config.yaml` | Local pre-commit enforcement of benchmark tests |

## Usage

### Local Development

```bash
# Run all unit tests
make test-all

# Run full benchmark pipeline (tests + trend report + regression check)
./scripts/run-benchmarks.sh

# Generate trend report with all exports
python3 scripts/bench-report.py \
  --output runs/trend-report.md \
  --json-out runs/trend-report.json \
  --prometheus-out runs/metrics.prom \
  --fail-on-regression
```

### Options for `bench-report.py`

| Flag | Description |
|---|---|
| `--output PATH` | Markdown report path (default: `runs/trend-report.md`) |
| `--json-out PATH` | Structured JSON export (optional) |
| `--prometheus-out PATH` | Prometheus exposition format export (optional) |
| `--history-out PATH` | Append-only JSONL historical trend log (default: `runs/perf-history.jsonl`) |
| `--fail-on-regression` | Exit code 1 if regression (>15% TPS drop from median) is detected |
| `--anomaly-threshold K` | IQR multiplier for outlier detection (default: 1.5) |
| `--budget-min-tps VAL` | Hard minimum throughput (tok/s); exit 1 if average below |
| `--budget-max-latency VAL` | Hard maximum latency (s); exit 1 if average above |

### Regression & SLA Enforcement

- **Regression detection**: If the latest TPS is < 85% of the median of earlier runs, a regression alert is emitted and `--fail-on-regression` triggers exit 1.
- **IQR anomaly detection**: Outliers beyond `Q1 - k*IQR` or `Q3 + k*IQR` are flagged in the report.
- **SLA budgets**: Hard thresholds (`--budget-min-tps`, `--budget-max-latency`) enforce service-level agreements in CI.

### Report Outputs

1. **Markdown (`runs/trend-report.md`)**:
   - Throughput summary (median, p95, p99, min, max)
   - Latency summary (median, p95, p99)
   - ASCII histogram distributions
   - Per-artifact metrics table
   - Moving average (3-run window) trend table
   - Anomaly detection results (IQR method)
   - Regression alerts (if any)
   - SLA budget violations (if any)
   - Historical trends over time (from JSONL log)

2. **JSON (`runs/trend-report.json`)**:
   - Machine-readable export with all stats, regression flag, SLA violation flag, and per-artifact metrics.

3. **Prometheus (`runs/metrics.prom`)**:
   - `strata_benchmark_artifacts_analyzed`
   - `strata_benchmark_regression_detected`
   - `strata_benchmark_sla_violated`
   - `strata_throughput_tok_s{quantile="p50|p95|p99|min|max|mean"}`
   - `strata_latency_seconds{quantile="p50|p95|p99|min|max|mean"}`

4. **Historical JSONL (`runs/perf-history.jsonl`)**:
   - Append-only log of each run's summary for long-term trend analysis.
## Historical Winning Configuration (Superseded) — 2× B580, 2026-11-24

> **Note:** This configuration (`r2-spec4-ec8192-pw2-ppr4-pool16-int8`,
> POOL_WORKERS=16) was an intermediate winner later superseded by
> `r3-spec4-ec8192-pw2-ppr4-pool20-int8` (POOL_WORKERS=20).  It is retained
> here for historical reference only.  See the "Verified Winning Configuration —
> Updated" section below for the current winner.

A grid search across 38 configurations identified a configuration that **strictly
dominates** the previous baseline (`baseline-ctx64k-auto-spec4-par1`) on both
decode and prefill throughput with coherence passing:

| Parameter | Value |
|---|---|
| SPEC | 4 |
| EXPERT_CACHE | 8192 |
| PEER_PREFILL_ROWS | 4 |
| POOL_WORKERS | 16 |
| PIPELINE_WINDOWS | 2 |
| KV | int8 |
| CTX | 65536 |

| Metric | Baseline | Winner | Δ |
|---|---|---|---|
| Decode (tok/s) | 11.9 | 12.8 | +7.6% |
| Prefill (tok/s) | 22.9 | 27.8 | +21.4% |

**Warm-run variance (3 repeats, winner `r2-spec4-ec8192-pw2-ppr4-pool16-int8`):**

| Run | Decode (tok/s) | Prefill (tok/s) | Coherence |
|---|---|---|---|
| 1 (cold) | 8.6 | 17.9 | PASS |
| 2 (warm) | 13.8 | 27.8 | PASS |
| 3 (warm) | 12.8 | 28.8 | PASS |
| **Median** | **12.8** | **27.8** | **PASS** |

Run 1 is consistently lower due to cold expert-cache; runs 2–3 are repeat-stable.

**Status:** Superseded by pool20 winner (see below).

## Verified Winning Configuration — Updated (2× B580, 2026-11-24)

After neighborhood search and warm-repeat validation, the verified winner was
updated from `r2-spec4-ec8192-pw2-ppr4-pool16-int8` to
`r3-spec4-ec8192-pw2-ppr4-pool20-int8` (POOL_WORKERS 16→20).

| Parameter | Value |
|---|---|
| SPEC | 4 |
| EXPERT_CACHE | 8192 |
| PEER_PREFILL_ROWS | 4 |
| POOL_WORKERS | 20 |
| PIPELINE_WINDOWS | 2 |
| KV | int8 |
| CTX | 65536 |

| Metric | Baseline | Winner (3-run) | Winner (10 warm runs) |
|---|---|---|---|
| Decode (tok/s) | 11.9 | 12.4 | 13.20 |
| Prefill (tok/s) | 22.9 | 31.4 | 31.55 |

**Winner-selection criterion:** Among coherence-passing entries that strictly
beat baseline on both decode and prefill, the winner maximises
`decode × prefill` (combined throughput product; tie-break: higher prefill_median).
Verified by `scripts/check_deployed_defaults.py` and `tests/test_deployed_defaults.py`.

**Variance-aware note:** The 3-run sweep median (12.4/31.4) is conservative;
warm repeats with proper warm-up show higher throughput (13.20/31.55). The
first run in each sweep is consistently lower due to cold expert-cache. 95% CI
for decode (10 warm runs): mean=12.39, stdev=2.53, CI≈[10.58, 14.20].
