#!/usr/bin/env python3
"""Predict near-term performance anomalies from historical alert data.

Uses exponential smoothing and linear trend to forecast the next winner
throughput values and flags predicted regressions against a baseline.
"""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DEFAULT = ROOT / "runs" / "regression-alert-history.jsonl"


def ewma(values, alpha=0.3):
    """Exponential weighted moving average."""
    if not values:
        return []
    out = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1 - alpha) * out[-1])
    return out


def linear_fit(values):
    """Return (slope, intercept) for a simple linear fit over index."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return 0.0, float(values[0])
    xs = list(range(n))
    ys = [float(v) for v in values]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    return slope, intercept


def predict_next(values):
    """Forecast the next value using linear trend."""
    slope, intercept = linear_fit(values)
    return intercept + slope * len(values)


def prediction_interval(values, z=1.96):
    """Return (lower, upper) prediction interval for the next value."""
    n = len(values)
    if n < 3:
        m = (sum(values) / n) if n else 0.0
        return m, m
    slope, intercept = linear_fit(values)
    preds = [intercept + slope * i for i in range(n)]
    residuals = [float(v) - p for v, p in zip(values, preds)]
    var = sum(r * r for r in residuals) / (n - 2)
    std = math.sqrt(var) if var > 0 else 0.0
    nxt = intercept + slope * n
    margin = z * std * math.sqrt(1 + 1 / n)
    return nxt - margin, nxt + margin


def load_history(path):
    records = []
    p = Path(path)
    if not p.exists():
        return records
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def detect_predicted_regression(history, baseline_decode, baseline_prefill,
                               horizon=1, threshold=0.0):
    """Forecast winner throughput and flag predicted baseline breaches."""
    decodes = [r.get("winner_decode", 0) for r in history if r.get("winner_decode", 0) > 0]
    prefills = [r.get("winner_prefill", 0) for r in history if r.get("winner_prefill", 0) > 0]

    pred_dec = predict_next(decodes) if decodes else 0.0
    pred_pre = predict_next(prefills) if prefills else 0.0
    lo_dec, hi_dec = prediction_interval(decodes) if len(decodes) >= 3 else (pred_dec, pred_dec)
    lo_pre, hi_pre = prediction_interval(prefills) if len(prefills) >= 3 else (pred_pre, pred_pre)

    dec_breach = pred_dec <= baseline_decode * (1 + threshold)
    pre_breach = pred_pre <= baseline_prefill * (1 + threshold)

    return {
        "horizon": horizon,
        "decode": {
            "history": decodes,
            "ewma": ewma(decodes),
            "predicted": pred_dec,
            "interval": [lo_dec, hi_dec],
            "baseline": baseline_decode,
            "predicted_regression": dec_breach,
        },
        "prefill": {
            "history": prefills,
            "ewma": ewma(prefills),
            "predicted": pred_pre,
            "interval": [lo_pre, hi_pre],
            "baseline": baseline_prefill,
            "predicted_regression": pre_breach,
        },
        "predicted_regression": bool(dec_breach or pre_breach),
    }


def main():
    ap = argparse.ArgumentParser(description="Predict performance anomalies from alert history")
    ap.add_argument("--history", default=str(HISTORY_DEFAULT))
    ap.add_argument("--baseline-decode", type=float, default=11.9)
    ap.add_argument("--baseline-prefill", type=float, default=22.9)
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="Allowed margin relative to baseline (default: 0.0)")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--fail-on-predicted-regression", action="store_true")
    args = ap.parse_args()

    history = load_history(args.history)
    result = detect_predicted_regression(
        history, args.baseline_decode, args.baseline_prefill, threshold=args.threshold)

    text = json.dumps(result, indent=2)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    print(text)
    if args.fail_on_predicted_regression and result["predicted_regression"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
