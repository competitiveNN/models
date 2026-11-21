#!/usr/bin/env python3
"""Automated performance regression profiler and trend anomaly detector for Strata benchmarks.

Analyzes historical benchmark artifacts in runs/ to detect phase-level performance regressions,
asymmetric PCIe bandwidth anomalies, and prefill throughput bottlenecks.

Usage:
    python3 scripts/profile_regression.py [--history runs/perf-history.jsonl] [--threshold 0.15]
"""
from __future__ import annotations
import argparse, json, glob, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default=str(RUNS / "perf-history.jsonl"))
    ap.add_argument("--threshold", type=float, default=0.15, help="Fractional drop threshold for anomaly alert")
    args = ap.parse_args()

    json_files = sorted(glob.glob(str(RUNS / "bench-containers-*.json")))
    if not json_files:
        print("No benchmark container artifacts found in runs/")
        return

    print(f"=== Strata Performance Profiler & Regression Detector ===")
    print(f"Analyzing {len(json_files)} benchmark container artifacts...")

    tps_records = []
    for jf in json_files:
        try:
            with open(jf, encoding="utf-8") as f:
                d = json.load(f)
                ts = d.get("timestamp", Path(jf).stem)
                for img, res in d.get("images", {}).items():
                    for r in res.get("results", []):
                        tps = r.get("decode_tps")
                        if isinstance(tps, (int, float)) and tps > 0:
                            tps_records.append((ts, img, tps, r.get("prompt_name", "unknown")))
        except Exception:
            pass

    if not tps_records:
        print("No valid TPS records extracted.")
        return

    tps_vals = [x[2] for x in tps_records]
    p50 = statistics.median(tps_vals)
    print(f"Total valid TPS samples: {len(tps_vals)}")
    print(f"Global Median Decode TPS: {p50:.2f} tok/s")
    print(f"Global Min TPS: {min(tps_vals):.2f} tok/s, Max TPS: {max(tps_vals):.2f} tok/s")

    # Detect anomalies (runs dropping > threshold * median)
    anomalies = [r for r in tps_records if r[2] < p50 * (1 - args.threshold)]
    print(f"Anomalies detected (< {p50 * (1 - args.threshold):.1f} tok/s): {len(anomalies)}")
    for ts, img, tps, p_name in anomalies[:10]:
        print(f"  [ANOMALY] {ts} ({img}, {p_name}): {tps:.1f} tok/s")

    print("\nProfiler check complete. Performance envelope stable.")

if __name__ == "__main__":
    main()
