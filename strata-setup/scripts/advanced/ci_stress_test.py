#!/usr/bin/env python3
"""Continuous Integration Stress-Testing Routine
Runs a configurable stress-test loop against the validation gate and telemetry
endpoints to ensure long-term stability under continuous load.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any


def run_stress_test(iterations: int = 3, output: str = "runs/ci_stress_test_report.json") -> int:
    print(f"Initializing CI Stress-Testing Routine ({iterations} iterations)...")
    results = []
    all_passed = True

    for i in range(1, iterations + 1):
        start = time.time()
        # Run a lightweight subset of checks for the stress loop (e.g. telemetry and bypass smoke)
        r_bypass = subprocess.run([sys.executable, "scripts/advanced/speculative_kv_bypass.py"], capture_output=True, text=True)
        r_telemetry = subprocess.run([sys.executable, "scripts/b580_advanced_telemetry.py", "--health-url", "http://127.0.0.1:9/health", "--timeout", "0.2"], capture_output=True, text=True)
        
        passed = r_bypass.returncode == 0 and r_telemetry.returncode == 0
        if not passed:
            all_passed = False
        
        results.append({
            "iteration": i,
            "duration_s": round(time.time() - start, 3),
            "bypass_ok": r_bypass.returncode == 0,
            "telemetry_ok": r_telemetry.returncode == 0,
            "passed": passed
        })
        print(f"[Stress] Iteration {i}/{iterations}: {'PASS' if passed else 'FAIL'}")

    report = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "PASSED" if all_passed else "FAILED",
        "iterations": iterations,
        "results": results
    }

    out_abs = os.path.abspath(output)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"[Stress] Report written to {out_abs}")
    print(f"========== CI STRESS-TEST {'PASSED' if all_passed else 'FAILED'} ==========")
    return 0 if all_passed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="CI Stress-Testing Routine")
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--output", default="runs/ci_stress_test_report.json")
    args = ap.parse_args()
    return run_stress_test(iterations=args.iterations, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
