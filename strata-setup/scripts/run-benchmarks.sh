#!/usr/bin/env bash
# ==============================================================================
# Strata Benchmark Automation Wrapper for CI / Local Validation
# ==============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Strata Benchmark & Regression Check ==="
echo "Working directory: $ROOT"

# Step 0: Run unit tests
echo "--- Running benchmark unit tests ---"
python3 -m unittest discover tests

# Step 1: Run benchmark trend analysis and regression detection with strict failure on regression
echo "--- Running bench-report.py ---"
python3 scripts/bench-report.py --output runs/trend-report.md --json-out runs/trend-report.json --prometheus-out runs/metrics.prom --fail-on-regression

REPORT_EXIT=$?

if [ $REPORT_EXIT -eq 0 ]; then
    echo "=== SUCCESS: Benchmark tests passed, report generated, and no regressions detected ==="
else
    echo "=== ERROR: Performance regression detected and --fail-on-regression triggered ==="
    exit $REPORT_EXIT
fi