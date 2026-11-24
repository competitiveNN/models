#!/usr/bin/env python3
"""Generate a historical performance trending visualization (markdown).

Reads runs/regression-alert-history.jsonl (and optionally sweep-summary.jsonl,
warm-*.json) and produces a markdown report with ASCII sparklines and tables
for winner/baseline throughput over time, plus drift summary.
"""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DEFAULT = ROOT / "runs" / "regression-alert-history.jsonl"

SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(values):
    """Render a list of numbers as an ASCII sparkline string."""
    if not values:
        return ""
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return SPARK_CHARS[0] * len(values)
    rng = hi - lo
    out = []
    for v in values:
        idx = int((v - lo) / rng * (len(SPARK_CHARS) - 1))
        idx = max(0, min(len(SPARK_CHARS) - 1, idx))
        out.append(SPARK_CHARS[idx])
    return "".join(out)


def detect_anomaly(values, z_threshold=2.5):
    """Return (is_anomaly, z_score, mean, std) for the last value vs prior values."""
    if len(values) < 5:
        return False, 0.0, (sum(values)/len(values) if values else 0.0), 0.0
    prior = values[:-1]
    mean = sum(prior) / len(prior)
    var = sum((v - mean) ** 2 for v in prior) / len(prior)
    std = var ** 0.5
    if std == 0:
        z = float("inf") if values[-1] != mean else 0.0
        return (values[-1] != mean), z, mean, std
    z = abs(values[-1] - mean) / std
    return z > z_threshold, z, mean, std


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


def generate_report(history_path=None, warm_dir=None):
    path = Path(history_path) if history_path is not None else HISTORY_DEFAULT
    records = load_history(path)
    lines = ["# Strata 2x B580 Performance Trend Report", ""]
    lines.append(f"Generated from: {path}")
    lines.append(f"Total history points: {len(records)}")
    lines.append("")

    if not records:
        lines.append("No history available yet.")
        return "\n".join(lines) + "\n"

    decodes = [r.get("winner_decode", 0) for r in records]
    prefills = [r.get("winner_prefill", 0) for r in records]
    base_decodes = [r.get("baseline_decode", 0) for r in records]
    base_prefills = [r.get("baseline_prefill", 0) for r in records]

    lines.append("## Winner throughput trend")
    lines.append(f"- decode:  {sparkline(decodes)}  (latest {decodes[-1]}, median {statistics.median(decodes):.2f})")
    lines.append(f"- prefill: {sparkline(prefills)}  (latest {prefills[-1]}, median {statistics.median(prefills):.2f})")
    lines.append("")
    lines.append("## Baseline throughput trend")
    lines.append(f"- decode:  {sparkline(base_decodes)}  (latest {base_decodes[-1]}, median {statistics.median(base_decodes):.2f})")
    lines.append(f"- prefill: {sparkline(base_prefills)}  (latest {base_prefills[-1]}, median {statistics.median(base_prefills):.2f})")
    lines.append("")

    # Ratios
    dec_ratios = [r.get("decode_ratio", 0) for r in records]
    pre_ratios = [r.get("prefill_ratio", 0) for r in records]
    lines.append("## Winner/baseline ratio trend")
    lines.append(f"- decode ratio:  {sparkline(dec_ratios)}  (latest {dec_ratios[-1]:.3f})")
    lines.append(f"- prefill ratio: {sparkline(pre_ratios)}  (latest {pre_ratios[-1]:.3f})")
    lines.append("")

    # Anomaly detection
    dec_anom, dec_z, dec_mean, dec_std = detect_anomaly(decodes)
    pre_anom, pre_z, pre_mean, pre_std = detect_anomaly(prefills)
    lines.append("## Anomaly detection (z-score)")
    lines.append(f"- decode:  z={dec_z:.2f} (mean={dec_mean:.2f}, std={dec_std:.2f}) "
                 f"{'ANOMALY' if dec_anom else 'ok'}")
    lines.append(f"- prefill: z={pre_z:.2f} (mean={pre_mean:.2f}, std={pre_std:.2f}) "
                 f"{'ANOMALY' if pre_anom else 'ok'}")
    lines.append("")

    # Alert/drift counts
    alerts = sum(1 for r in records if r.get("alert"))
    drifts = sum(1 for r in records if r.get("drift_detected"))
    lines.append("## Alert summary")
    lines.append(f"- total runs: {len(records)}")
    lines.append(f"- alerts: {alerts}")
    lines.append(f"- drifts: {drifts}")
    lines.append("")

    # Recent table
    lines.append("## Recent runs")
    lines.append("| timestamp | winner decode | winner prefill | alert | drift |")
    lines.append("|---|---|---|---|---|")
    for r in records[-10:]:
        lines.append(
            f"| {r.get('timestamp','')} | {r.get('winner_decode')} | {r.get('winner_prefill')} "
            f"| {r.get('alert')} | {r.get('drift_detected')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Generate performance trend report")
    ap.add_argument("--history", default=str(HISTORY_DEFAULT), help="Path to regression-alert history JSONL")
    ap.add_argument("--out", default=None, help="Write markdown to this path (default: stdout)")
    ap.add_argument("--json-out", default=None, help="Also write JSON summary to this path")
    args = ap.parse_args()

    report = generate_report(args.history)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
    print(report)

    if args.json_out:
        records = load_history(args.history)
        decodes = [r.get("winner_decode", 0) for r in records]
        prefills = [r.get("winner_prefill", 0) for r in records]
        dec_anom, dec_z, _, _ = detect_anomaly(decodes)
        pre_anom, pre_z, _, _ = detect_anomaly(prefills)
        summary = {
            "points": len(records),
            "winner_decode_latest": records[-1].get("winner_decode") if records else None,
            "winner_prefill_latest": records[-1].get("winner_prefill") if records else None,
            "alerts": sum(1 for r in records if r.get("alert")),
            "drifts": sum(1 for r in records if r.get("drift_detected")),
            "decode_anomaly": dec_anom,
            "decode_z": round(dec_z, 3),
            "prefill_anomaly": pre_anom,
            "prefill_z": round(pre_z, 3),
        }
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
