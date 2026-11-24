#!/usr/bin/env python3
"""Compute per-entry variance and confidence intervals from sweep-summary.jsonl.

Reads runs/sweep-summary.jsonl, computes for each entry:
  - mean, median, std, min, max of per-run decode/prefill
  - 95% confidence interval (t-distribution, small sample)
  - coefficient of variation (CV)

Outputs a summary table and optionally a JSON file.

Usage:
  python3 scripts/compute_variance_ci.py [--json-out runs/variance-ci.json]
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "runs" / "sweep-summary.jsonl"

# t-critical values for 95% CI, two-tailed, by degrees of freedom
T_CRIT = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776,
    5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
    9: 2.262, 10: 2.228, 15: 2.131, 20: 2.086,
    30: 2.042, 60: 2.000, 120: 1.980,
}


def t_crit(df):
    if df in T_CRIT:
        return T_CRIT[df]
    # interpolate / fallback
    if df <= 1:
        return 12.706
    if df >= 120:
        return 1.96
    # nearest
    keys = sorted(T_CRIT.keys())
    for i in range(len(keys) - 1):
        if keys[i] <= df <= keys[i + 1]:
            lo, hi = keys[i], keys[i + 1]
            frac = (df - lo) / (hi - lo)
            return T_CRIT[lo] + frac * (T_CRIT[hi] - T_CRIT[lo])
    return 2.0


def stats(values):
    """Compute mean, std, ci_half, min, max for a list of values."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "median": 0.0, "std": 0.0,
                "ci_half": 0.0, "ci_lo": 0.0, "ci_hi": 0.0,
                "min": 0.0, "max": 0.0, "cv": 0.0}
    mean = sum(values) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        std = math.sqrt(var)
    else:
        std = 0.0
    # median
    sorted_v = sorted(values)
    if n % 2 == 0:
        median = (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    else:
        median = sorted_v[n // 2]
    # 95% CI
    if n > 1 and std > 0:
        se = std / math.sqrt(n)
        ci_half = t_crit(n - 1) * se
    else:
        ci_half = 0.0
    cv = (std / mean * 100) if mean > 0 else 0.0
    return {
        "n": n,
        "mean": round(mean, 2),
        "median": round(median, 2),
        "std": round(std, 2),
        "ci_half": round(ci_half, 2),
        "ci_lo": round(mean - ci_half, 2),
        "ci_hi": round(mean + ci_half, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "cv": round(cv, 1),
    }


def main():
    ap = argparse.ArgumentParser(description="Compute variance and CI for sweep entries")
    ap.add_argument("--json-out", default=None, help="Write JSON output to this path")
    ap.add_argument("--tag", default=None, help="Filter to a single tag")
    args = ap.parse_args()

    entries = []
    for line in SUMMARY.read_text().splitlines():
        if not line.strip():
            continue
        entries.append(json.loads(line))

    if args.tag:
        entries = [e for e in entries if e.get("tag") == args.tag]

    results = []
    for e in entries:
        decodes = [v for v in e.get("per_run_decode", []) if isinstance(v, (int, float)) and v > 0]
        prefills = [v for v in e.get("per_run_prefill", []) if isinstance(v, (int, float)) and v > 0]
        d_stats = stats(decodes)
        p_stats = stats(prefills)
        results.append({
            "tag": e.get("tag"),
            "coherence_pass": e.get("coherence_pass", False),
            "decode": d_stats,
            "prefill": p_stats,
            "median_decode": e.get("decode_median"),
            "median_prefill": e.get("prefill_median"),
        })

    # Print table
    print(f"{'Tag':<45} {'Dec med':>8} {'Dec CI':>14} {'Dec CV%':>8} {'Pre med':>8} {'Pre CI':>14} {'Pre CV%':>8} {'Coh':>4}")
    print("-" * 120)
    for r in sorted(results, key=lambda x: -x["median_decode"]):
        d = r["decode"]
        p = r["prefill"]
        coh = "Y" if r["coherence_pass"] else "N"
        print(f"{r['tag']:<45} {r['median_decode']:>8.1f} {d['ci_lo']:>6.1f}-{d['ci_hi']:<6.1f} {d['cv']:>7.1f}% "
              f"{r['median_prefill']:>8.1f} {p['ci_lo']:>6.1f}-{p['ci_hi']:<6.1f} {p['cv']:>7.1f}% {coh:>4}")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"\nJSON written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
