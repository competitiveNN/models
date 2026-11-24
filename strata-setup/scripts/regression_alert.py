#!/usr/bin/env python3
"""Emit performance regression alert metrics for CI trend tracking.

Reads runs/sweep-summary.jsonl and runs/warm-*.json, computes winner vs
baseline metrics, and writes a JSON report to runs/regression-alert.json
(and prints to stdout) for CI consumption and trend tracking.

The report includes:
  * winner and baseline decode/prefill medians
  * improvement ratios and percentages
  * warm-repeat medians (when available)
  * pass/fail status for each check
  * overall alert flag (true if any check fails)

Usage:
  python3 scripts/regression_alert.py [--json-out runs/regression-alert.json]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_FILE = ROOT / "runs" / "sweep-summary.jsonl"
WINNER_TAG = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"


def load_entries():
    """Load all entries from sweep-summary.jsonl."""
    entries = []
    if not SUMMARY_FILE.exists():
        return entries
    for line in SUMMARY_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def find_entry(entries, tag):
    for e in entries:
        if e.get("tag") == tag:
            return e
    return None


def load_warm_median(tag):
    """Return warm-repeat median decode/prefill for a tag, or None."""
    import glob
    for p in sorted(Path("runs").glob("warm-*.json")):
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("tag") == tag:
            decodes = [r["decode"] for r in data.get("per_run", []) if r.get("decode", 0) > 0]
            prefills = [r["prefill"] for r in data.get("per_run", []) if r.get("prefill", 0) > 0]
            if decodes and prefills:
                return {
                    "decode_median": statistics.median(decodes),
                    "prefill_median": statistics.median(prefills),
                    "decode_stdev": statistics.stdev(decodes) if len(decodes) > 1 else 0.0,
                    "prefill_stdev": statistics.stdev(prefills) if len(prefills) > 1 else 0.0,
                    "n": len(decodes),
                }
    return None


def main():
    ap = argparse.ArgumentParser(description="Emit performance regression alert metrics")
    ap.add_argument("--json-out", default="runs/regression-alert.json",
                    help="Path to write JSON report (default: runs/regression-alert.json)")
    args = ap.parse_args()

    entries = load_entries()
    baseline = find_entry(entries, BASELINE_TAG)
    winner = find_entry(entries, WINNER_TAG)

    report = {
        "schema_version": 1,
        "winner_tag": WINNER_TAG,
        "baseline_tag": BASELINE_TAG,
        "alert": False,
        "checks": {},
    }

    if not baseline:
        report["alert"] = True
        report["error"] = f"Baseline tag '{BASELINE_TAG}' not found in sweep summary"
        report["checks"]["baseline_found"] = {"passed": False, "message": report["error"]}
    else:
        report["checks"]["baseline_found"] = {"passed": True, "message": "Baseline found"}

    if not winner:
        report["alert"] = True
        report["error"] = f"Winner tag '{WINNER_TAG}' not found in sweep summary"
        report["checks"]["winner_found"] = {"passed": False, "message": report["error"]}
    else:
        report["checks"]["winner_found"] = {"passed": True, "message": "Winner found"}

    if baseline and winner:
        base_dec = baseline.get("decode_median", 0)
        base_pre = baseline.get("prefill_median", 0)
        win_dec = winner.get("decode_median", 0)
        win_pre = winner.get("prefill_median", 0)
        win_coh = winner.get("coherence_pass", False)

        dec_ratio = win_dec / base_dec if base_dec > 0 else 0
        pre_ratio = win_pre / base_pre if base_pre > 0 else 0

        report["metrics"] = {
            "baseline": {
                "decode_median": base_dec,
                "prefill_median": base_pre,
            },
            "winner": {
                "decode_median": win_dec,
                "prefill_median": win_pre,
                "coherence_pass": win_coh,
            },
            "ratios": {
                "decode": dec_ratio,
                "prefill": pre_ratio,
            },
            "improvement_pct": {
                "decode": (dec_ratio - 1.0) * 100,
                "prefill": (pre_ratio - 1.0) * 100,
            },
        }

        # Winner checks
        decode_beats = win_dec > base_dec
        prefill_beats = win_pre > base_pre
        coherence_ok = win_coh

        report["checks"]["decode_beats_baseline"] = {
            "passed": decode_beats,
            "winner": win_dec,
            "baseline": base_dec,
            "ratio": dec_ratio,
            "message": f"Winner decode {win_dec:.1f} > baseline {base_dec:.1f}"
            if decode_beats else f"FAIL: winner decode {win_dec:.1f} <= baseline {base_dec:.1f}",
        }
        report["checks"]["prefill_beats_baseline"] = {
            "passed": prefill_beats,
            "winner": win_pre,
            "baseline": base_pre,
            "ratio": pre_ratio,
            "message": f"Winner prefill {win_pre:.1f} > baseline {base_pre:.1f}"
            if prefill_beats else f"FAIL: winner prefill {win_pre:.1f} <= baseline {base_pre:.1f}",
        }
        report["checks"]["winner_coherence"] = {
            "passed": coherence_ok,
            "message": "Winner coherence pass" if coherence_ok else "FAIL: winner coherence fail",
        }

        # Warm-repeat checks
        warm_winner = load_warm_median(WINNER_TAG)
        warm_baseline = load_warm_median(BASELINE_TAG)

        if warm_winner:
            report["metrics"]["winner_warm"] = warm_winner
            report["checks"]["winner_warm_decode_positive"] = {
                "passed": warm_winner["decode_median"] > 0,
                "decode_median": warm_winner["decode_median"],
            }
            report["checks"]["winner_warm_prefill_positive"] = {
                "passed": warm_winner["prefill_median"] > 0,
                "prefill_median": warm_winner["prefill_median"],
            }
            if warm_baseline:
                warm_dec_ratio = warm_winner["decode_median"] / warm_baseline["decode_median"] if warm_baseline["decode_median"] > 0 else 0
                warm_pre_ratio = warm_winner["prefill_median"] / warm_baseline["prefill_median"] if warm_baseline["prefill_median"] > 0 else 0
                report["metrics"]["winner_warm_improvement_pct"] = {
                    "decode": (warm_dec_ratio - 1.0) * 100,
                    "prefill": (warm_pre_ratio - 1.0) * 100,
                }

        if warm_baseline:
            report["metrics"]["baseline_warm"] = warm_baseline

        # Overall alert: any critical check fails
        critical = [
            report["checks"]["decode_beats_baseline"]["passed"],
            report["checks"]["prefill_beats_baseline"]["passed"],
            report["checks"]["winner_coherence"]["passed"],
        ]
        report["alert"] = not all(critical)

    # Write JSON report
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    # Print summary
    print(json.dumps(report, indent=2))

    if report["alert"]:
        print("\nALERT: Performance regression detected!", file=sys.stderr)
        return 1
    print("\nNo performance regression detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
