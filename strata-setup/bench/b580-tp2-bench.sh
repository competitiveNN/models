#!/usr/bin/env bash
# Automated performance and VRAM tracking benchmark for 2x Intel Arc B580 TP2.
# Runs standardized benchmarks and stores results for continuous monitoring.
#
# Usage:
#   ./bench/b580-tp2-bench.sh            # Run benchmarks and store results
#   ./bench/b580-tp2-bench.sh --compare  # Compare against baseline
#   ./bench/b580-tp2-bench.sh --trend    # Show trend report

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH_DIR="$ROOT/bench"
RESULTS_DIR="$ROOT/runs"
URL="${URL:-http://127.0.0.1:1235/v1/chat/completions}"

mkdir -p "$RESULTS_DIR"

case "${1:-run}" in
  run)
    echo "[bench] Running 2x B580 TP2 benchmark suite..."
    python3 "$ROOT/scripts/bench-automation.py" --run --url "$URL"
    python3 "$ROOT/scripts/b580_dashboard.py" > "$RESULTS_DIR/dashboard.md"
    python3 "$ROOT/scripts/benchmark_trend.py" > "$RESULTS_DIR/benchmark-trend.md"
    python3 "$ROOT/scripts/vram_balancer.py" > "$RESULTS_DIR/vram-report.json"
    python3 "$ROOT/scripts/b580_thermal.py" > "$RESULTS_DIR/thermal-metrics.prom" 2>/dev/null || true
    python3 "$ROOT/scripts/b580_prometheus.py" > "$RESULTS_DIR/telemetry-metrics.prom" 2>/dev/null || true
    echo "[bench] Results saved to $RESULTS_DIR/"
    ;;
  compare)
    echo "[bench] Comparing against baseline..."
    python3 "$ROOT/scripts/bench-automation.py" --compare --url "$URL"
    ;;
  trend)
    echo "[bench] Generating trend report..."
    python3 "$ROOT/scripts/benchmark_trend.py"
    ;;
  baseline)
    echo "[bench] Setting current results as baseline..."
    python3 "$ROOT/scripts/bench-automation.py" --baseline
    ;;
  *)
    echo "Usage: $0 {run|compare|trend|baseline}"
    exit 1
    ;;
esac
