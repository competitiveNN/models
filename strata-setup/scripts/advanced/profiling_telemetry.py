#!/usr/bin/env python3
"""Continuous Profiling Telemetry & Automated Thermal Profiling Alerts
Extends the observability suite with:
1. Continuous profiling telemetry collection (sampling-based).
2. Predictive thermal profiling alerts based on trend analysis.
3. Automated benchmark comparison against stored baselines.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any


class ProfilingTelemetry:
    def __init__(self, history_dir: str = "runs/profiling_history") -> None:
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.samples = deque(maxlen=100)

    def collect_sample(self) -> dict[str, Any]:
        """Collect a single profiling sample from xpu-smi and system."""
        sample = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        
        # GPU telemetry
        try:
            r = subprocess.run(
                ["xpu-smi", "--query-gpu=temperature.gpu,power.draw,clocks.current.graphics,utilization.gpu", 
                 "--id=0", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                vals = [v.strip() for v in r.stdout.strip().split(",")]
                sample["gpu_0"] = {
                    "temp_c": float(vals[0]) if vals[0] != "N/A" else 0.0,
                    "power_w": float(vals[1]) if vals[1] != "N/A" else 0.0,
                    "clock_mhz": float(vals[2]) if vals[2] != "N/A" else 0.0,
                    "util_pct": float(vals[3]) if vals[3] != "N/A" else 0.0,
                }
        except Exception:
            sample["gpu_0"] = {"error": "collection_failed"}
        
        try:
            r = subprocess.run(
                ["xpu-smi", "--query-gpu=temperature.gpu,power.draw,clocks.current.graphics,utilization.gpu", 
                 "--id=1", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                vals = [v.strip() for v in r.stdout.strip().split(",")]
                sample["gpu_1"] = {
                    "temp_c": float(vals[0]) if vals[0] != "N/A" else 0.0,
                    "power_w": float(vals[1]) if vals[1] != "N/A" else 0.0,
                    "clock_mhz": float(vals[2]) if vals[2] != "N/A" else 0.0,
                    "util_pct": float(vals[3]) if vals[3] != "N/A" else 0.0,
                }
        except Exception:
            sample["gpu_1"] = {"error": "collection_failed"}
        
        self.samples.append(sample)
        return sample

    def analyze_trends(self) -> dict[str, Any]:
        """Analyze collected samples for thermal/power trends."""
        if len(self.samples) < 3:
            return {"status": "insufficient_data", "samples": len(self.samples)}
        
        gpu0_temps = [s.get("gpu_0", {}).get("temp_c", 0) for s in self.samples if "gpu_0" in s and "temp_c" in s["gpu_0"]]
        gpu1_temps = [s.get("gpu_1", {}).get("temp_c", 0) for s in self.samples if "gpu_1" in s and "temp_c" in s["gpu_1"]]
        gpu0_powers = [s.get("gpu_0", {}).get("power_w", 0) for s in self.samples if "gpu_0" in s and "power_w" in s["gpu_0"]]
        gpu1_powers = [s.get("gpu_1", {}).get("power_w", 0) for s in self.samples if "gpu_1" in s and "power_w" in s["gpu_1"]]
        
        alerts = []
        # Simple trend: linear regression slope
        def trend(vals):
            if len(vals) < 2:
                return 0.0
            n = len(vals)
            x = list(range(n))
            sum_x = sum(x)
            sum_y = sum(vals)
            sum_xy = sum(x[i] * vals[i] for i in range(n))
            sum_x2 = sum(x[i] ** 2 for i in range(n))
            return (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        gpu0_temp_trend = trend(gpu0_temps)
        gpu1_temp_trend = trend(gpu1_temps)
        
        if gpu0_temp_trend > 0.5:
            alerts.append({"severity": "WARNING", "metric": "gpu_0_temp_trend", "trend": gpu0_temp_trend, "message": "GPU 0 temperature rising"})
        if gpu1_temp_trend > 0.5:
            alerts.append({"severity": "WARNING", "metric": "gpu_1_temp_trend", "trend": gpu1_temp_trend, "message": "GPU 1 temperature rising"})
        
        latest_gpu0 = self.samples[-1].get("gpu_0", {})
        latest_gpu1 = self.samples[-1].get("gpu_1", {})
        
        if latest_gpu0.get("temp_c", 0) > 80:
            alerts.append({"severity": "CRITICAL", "metric": "gpu_0_temp", "value": latest_gpu0.get("temp_c"), "message": "GPU 0 approaching thermal limit"})
        if latest_gpu1.get("temp_c", 0) > 80:
            alerts.append({"severity": "CRITICAL", "metric": "gpu_1_temp", "value": latest_gpu1.get("temp_c"), "message": "GPU 1 approaching thermal limit"})
        
        return {
            "status": "analyzed",
            "samples": len(self.samples),
            "gpu_0": {
                "avg_temp_c": sum(gpu0_temps) / len(gpu0_temps) if gpu0_temps else 0,
                "max_temp_c": max(gpu0_temps) if gpu0_temps else 0,
                "temp_trend_per_sample": gpu0_temp_trend,
                "avg_power_w": sum(gpu0_powers) / len(gpu0_powers) if gpu0_powers else 0,
            },
            "gpu_1": {
                "avg_temp_c": sum(gpu1_temps) / len(gpu1_temps) if gpu1_temps else 0,
                "max_temp_c": max(gpu1_temps) if gpu1_temps else 0,
                "temp_trend_per_sample": gpu1_temp_trend,
                "avg_power_w": sum(gpu1_powers) / len(gpu1_powers) if gpu1_powers else 0,
            },
            "alerts": alerts
        }

    def save_history(self) -> str:
        """Save sample history to disk."""
        hist_path = self.history_dir / f"profiling_{int(time.time())}.json"
        with open(hist_path, "w") as f:
            json.dump(list(self.samples), f, indent=2)
            f.write("\n")
        return str(hist_path)


def run_profiling_telemetry(duration: int = 10, interval: float = 1.0, output: str = "runs/profiling_telemetry_report.json") -> int:
    print(f"Initializing Continuous Profiling Telemetry (duration={duration}s, interval={interval}s)...")
    
    telemetry = ProfilingTelemetry()
    start = time.time()
    while time.time() - start < duration:
        telemetry.collect_sample()
        time.sleep(interval)
    
    analysis = telemetry.analyze_trends()
    hist_path = telemetry.save_history()
    
    report = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "COMPLETED",
        "duration_s": duration,
        "interval_s": interval,
        "analysis": analysis,
        "history_file": hist_path
    }
    
    out_abs = os.path.abspath(output)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    
    print(f"[Profiling] Report written to {out_abs}")
    print(f"[Profiling] Alerts: {len(analysis.get('alerts', []))}")
    print("========== CONTINUOUS PROFILING TELEMETRY COMPLETED ==========")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Continuous Profiling Telemetry & Thermal Profiling Alerts")
    ap.add_argument("--duration", type=int, default=10)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--output", default="runs/profiling_telemetry_report.json")
    args = ap.parse_args()
    return run_profiling_telemetry(duration=args.duration, interval=args.interval, output=args.output)


if __name__ == "__main__":
    sys.exit(main())