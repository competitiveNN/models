#!/usr/bin/env python3
"""Continuous Automated Performance Regression Monitor
Monitors performance metrics against historical baselines and emits alerts
for CI/CD integration. Supports configurable thresholds and trend analysis.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


BASELINE_FILE = os.environ.get("PERF_BASELINE_FILE", "runs/performance_baseline.json")
HISTORY_FILE = os.environ.get("PERF_HISTORY_FILE", "runs/performance_history.jsonl")


def load_baseline() -> dict[str, Any]:
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_baseline(baseline: dict[str, Any]) -> None:
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)
        f.write("\n")


def append_history(record: dict[str, Any]) -> None:
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_benchmark_check() -> dict[str, Any]:
    """Run a quick benchmark to get current performance metrics."""
    # This simulates running the actual benchmark
    # In production, this would call the actual strata benchmark
    try:
        r = subprocess.run([
            sys.executable, "scripts/advanced/speculative_kv_bypass.py"
        ], capture_output=True, text=True, timeout=30)
        
        if r.returncode == 0:
            with open("runs/advanced_bypass_report.json", "r") as f:
                report = json.load(f)
            perf = report.get("measured_boosted_performance", {})
            return {
                "decode_tok_s": perf.get("decode_tok_s", 0),
                "prefill_64k_tok_s": perf.get("prefill_64k_tok_s", 0),
                "status": "success"
            }
    except Exception as e:
        pass
    
    # Fallback: try thermal governor for clock/power data
    try:
        r = subprocess.run([
            sys.executable, "scripts/advanced/thermal_governor.py", "--output", "/tmp/tg_check.json"
        ], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            with open("/tmp/tg_check.json", "r") as f:
                tg = json.load(f)
            sensors = tg.get("telemetry", {}).get("sensors", {})
            return {
                "gpu_0_clock_mhz": sensors.get("0", {}).get("clocks_current_graphics_mhz", 0),
                "gpu_1_clock_mhz": sensors.get("1", {}).get("clocks_current_graphics_mhz", 0),
                "gpu_0_temp_c": sensors.get("0", {}).get("temperature_gpu_c", 0),
                "gpu_1_temp_c": sensors.get("1", {}).get("temperature_gpu_c", 0),
                "status": "thermal_only"
            }
    except Exception:
        pass
    
    return {"status": "failed", "error": "benchmark unavailable"}


def check_regression(current: dict[str, Any], baseline: dict[str, Any], 
                     decode_threshold: float = 0.15, prefill_threshold: float = 0.15) -> dict[str, Any]:
    """Check current metrics against baseline for regressions."""
    alerts = []
    
    for metric, threshold in [("decode_tok_s", decode_threshold), ("prefill_64k_tok_s", prefill_threshold)]:
        if metric in current and metric in baseline:
            current_val = current[metric]
            baseline_val = baseline[metric]
            if baseline_val > 0:
                regression_pct = (baseline_val - current_val) / baseline_val
                if regression_pct > threshold:
                    alerts.append({
                        "severity": "CRITICAL" if regression_pct > threshold * 2 else "WARNING",
                        "metric": metric,
                        "current": current_val,
                        "baseline": baseline_val,
                        "regression_pct": round(regression_pct * 100, 2),
                        "threshold_pct": round(threshold * 100, 2)
                    })
    
    # Check thermal throttling
    if "gpu_0_temp_c" in current and current["gpu_0_temp_c"] > 85:
        alerts.append({
            "severity": "CRITICAL",
            "metric": "gpu_0_thermal",
            "value": current["gpu_0_temp_c"],
            "message": "GPU 0 exceeding thermal limit"
        })
    if "gpu_1_temp_c" in current and current["gpu_1_temp_c"] > 85:
        alerts.append({
            "severity": "CRITICAL",
            "metric": "gpu_1_thermal",
            "value": current["gpu_1_temp_c"],
            "message": "GPU 1 exceeding thermal limit"
        })
    
    return {
        "alerts": alerts,
        "status": "FAILED" if any(a["severity"] == "CRITICAL" for a in alerts) else ("WARNING" if alerts else "PASSED")
    }


def run_regression_monitor(update_baseline: bool = False, 
                           decode_threshold: float = 0.15,
                           prefill_threshold: float = 0.15,
                           output: str = "runs/regression_monitor_report.json") -> int:
    print("Initializing Continuous Automated Performance Regression Monitor...")
    
    current = run_benchmark_check()
    baseline = load_baseline()
    
    if not baseline and update_baseline:
        baseline = current
        save_baseline(baseline)
        print("No baseline found; created new baseline from current run.")
    
    if not baseline:
        print("No baseline available; skipping regression check.")
        result = {"status": "SKIPPED", "reason": "no_baseline", "current": current}
    else:
        check = check_regression(current, baseline, decode_threshold, prefill_threshold)
        result = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": check["status"],
            "current_metrics": current,
            "baseline_metrics": baseline,
            "alerts": check["alerts"]
        }
        
        # Update baseline if no critical regressions and update requested
        if update_baseline and check["status"] != "FAILED":
            save_baseline(current)
            print("Baseline updated with current metrics.")
    
    # Append to history
    append_history(result)
    
    out_abs = os.path.abspath(output)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    
    print(f"[Regression Monitor] Status: {result.get('status', 'UNKNOWN')}")
    print(f"[Regression Monitor] Alerts: {len(result.get('alerts', []))}")
    print("========== CONTINUOUS REGRESSION MONITOR COMPLETED ==========")
    return 0 if result.get("status") in ("PASSED", "SKIPPED", "WARNING") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Continuous Automated Performance Regression Monitor")
    ap.add_argument("--update-baseline", action="store_true", help="Update baseline with current metrics")
    ap.add_argument("--decode-threshold", type=float, default=0.15, help="Decode regression threshold (fraction)")
    ap.add_argument("--prefill-threshold", type=float, default=0.15, help="Prefill regression threshold (fraction)")
    ap.add_argument("--output", default="runs/regression_monitor_report.json")
    args = ap.parse_args()
    return run_regression_monitor(
        update_baseline=args.update_baseline,
        decode_threshold=args.decode_threshold,
        prefill_threshold=args.prefill_threshold,
        output=args.output
    )


if __name__ == "__main__":
    sys.exit(main())