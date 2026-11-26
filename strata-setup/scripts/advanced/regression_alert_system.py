#!/usr/bin/env python3
"""Automated Multi-Node Benchmark Regression Alert System
Monitors aggregated dashboard reports for performance regressions and emits
machine-readable alerts for CI/CD pipelines and external monitoring webhooks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any


def run_regression_alert(output_path: str = "runs/regression_alert_report.json") -> int:
    print("Initializing Automated Multi-Node Benchmark Regression Alert System...")
    
    dashboard_path = "runs/observability_dashboard_report.json"
    alerts = []
    status = "PASSED"
    
    if os.path.exists(dashboard_path):
        try:
            with open(dashboard_path, "r") as f:
                dashboard = json.load(f)
            metrics = dashboard.get("metrics_summary", {})
            
            decode = metrics.get("decode_tok_s", 0)
            prefill = metrics.get("prefill_64k_tok_s", 0)
            
            if decode < 50.0:
                alerts.append({"severity": "CRITICAL", "metric": "decode_tok_s", "value": decode, "threshold": 50.0})
                status = "FAILED"
            if prefill < 2000.0:
                alerts.append({"severity": "CRITICAL", "metric": "prefill_64k_tok_s", "value": prefill, "threshold": 2000.0})
                status = "FAILED"
        except Exception as e:
            alerts.append({"severity": "ERROR", "message": f"Failed to parse dashboard: {e}"})
            status = "FAILED"
    else:
        alerts.append({"severity": "WARNING", "message": "Dashboard report not found; skipping regression check."})

    report = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "alerts_triggered": len(alerts),
        "alerts": alerts
    }

    out_abs = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"[Alerts] Regression alert report written to {out_abs}")
    print(f"[Alerts] Status: {status}, Alerts Triggered: {len(alerts)}")
    print(f"========== REGRESSION ALERT CHECK {'PASSED' if status == 'PASSED' else 'FAILED'} ==========")
    return 0 if status == "PASSED" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Automated Multi-Node Benchmark Regression Alert System")
    ap.add_argument("--output", default="runs/regression_alert_report.json")
    args = ap.parse_args()
    return run_regression_alert(output_path=args.output)


if __name__ == "__main__":
    sys.exit(main())
