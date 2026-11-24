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
  * drift detection vs recent history (when available)
  * webhook notification (optional)

Usage:
  python3 scripts/regression_alert.py [--json-out runs/regression-alert.json]
  python3 scripts/regression_alert.py --webhook-url https://hooks.example.com/...
  python3 scripts/regression_alert.py --dry-run
"""
import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_FILE = ROOT / "runs" / "sweep-summary.jsonl"
RUNS_DIR = ROOT / "runs"
WINNER_TAG = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"
HISTORY_FILE_DEFAULT = ROOT / "runs" / "regression-alert-history.jsonl"

CRITICAL_CHECKS = ("decode_beats_baseline", "prefill_beats_baseline", "winner_coherence")


def load_entries(summary_path=None):
    """Load all entries from sweep-summary.jsonl."""
    path = Path(summary_path) if summary_path is not None else SUMMARY_FILE
    entries = []
    if not path.exists():
        return entries
    for line in path.read_text().splitlines():
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


def _load_warm_files(runs_dir=None):
    base = Path(runs_dir) if runs_dir is not None else RUNS_DIR
    out = {}
    for p in sorted(base.glob("warm-*.json")):
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        tag = data.get("tag")
        if tag:
            out[tag] = data
    return out


def _warm_entry_to_median(data):
    decodes = [r["decode"] for r in data.get("per_run", []) if r.get("decode", 0) > 0]
    prefills = [r["prefill"] for r in data.get("per_run", []) if r.get("prefill", 0) > 0]
    if not decodes or not prefills:
        return None
    return {
        "decode_median": statistics.median(decodes),
        "prefill_median": statistics.median(prefills),
        "decode_stdev": statistics.stdev(decodes) if len(decodes) > 1 else 0.0,
        "prefill_stdev": statistics.stdev(prefills) if len(prefills) > 1 else 0.0,
        "n": len(decodes),
    }


def _match_warm_file(tag, warm_files, entries=None):
    """Find the warm file best matching a sweep tag (by tag, env, or name)."""
    if tag in warm_files:
        return warm_files[tag]
    # env-based matching
    target_env = {}
    if entries:
        e = find_entry(entries, tag)
        if e:
            target_env = e.get("env", {}) or {}
    best = None
    best_score = -1
    for t, data in warm_files.items():
        wenv = data.get("env", {}) or {}
        common = set(wenv) & set(target_env)
        if common:
            score = sum(1 for k in common if str(wenv.get(k)) == str(target_env.get(k)))
            if score == len(common) and score > best_score:
                best_score = score
                best = data
        else:
            # fallback: tag name heuristic
            pass
    if best is not None:
        return best
    # Heuristic by tag substring
    low = tag.lower()
    for t, data in warm_files.items():
        dt = str(data.get("tag", "")).lower()
        if "baseline" in low and "baseline" in dt:
            return data
        if ("winner" in low or "pool" in low) and ("winner" in dt or "pool" in dt):
            return data
    return None


def load_warm_median(tag, runs_dir=None, entries=None):
    """Return warm-repeat median decode/prefill for a tag, or None."""
    if entries is None:
        try:
            entries = load_entries()
        except Exception:
            entries = None
    warm_files = _load_warm_files(runs_dir)
    data = _match_warm_file(tag, warm_files, entries)
    if data is None:
        return None
    return _warm_entry_to_median(data)


def load_history(history_path=None):
    """Load regression alert history (list of records)."""
    path = Path(history_path) if history_path is not None else HISTORY_FILE_DEFAULT
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def append_history(record, history_path=None):
    """Append a compact record to the history file."""
    path = Path(history_path) if history_path is not None else HISTORY_FILE_DEFAULT
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def detect_drift(history, current_winner_decode, current_winner_prefill,
                 threshold=0.10, window=5):
    """Compare current winner medians to rolling median of recent history.

    Returns dict with status, ratios, and whether drift was detected.
    """
    result = {
        "status": "insufficient_data",
        "decode_ratio": None,
        "prefill_ratio": None,
        "drift_detected": False,
        "points": len(history),
        "threshold": threshold,
    }
    if len(history) < 2:
        return result
    recent = history[-window:]
    decodes = [h.get("winner_decode", 0) for h in recent if h.get("winner_decode", 0) > 0]
    prefills = [h.get("winner_prefill", 0) for h in recent if h.get("winner_prefill", 0) > 0]
    if not decodes or not prefills:
        return result
    base_dec = statistics.median(decodes)
    base_pre = statistics.median(prefills)
    dec_ratio = current_winner_decode / base_dec if base_dec > 0 else 1.0
    pre_ratio = current_winner_prefill / base_pre if base_pre > 0 else 1.0
    drift = dec_ratio < (1 - threshold) or pre_ratio < (1 - threshold)
    result.update({
        "status": "drift" if drift else "ok",
        "decode_ratio": round(dec_ratio, 4),
        "prefill_ratio": round(pre_ratio, 4),
        "drift_detected": drift,
        "baseline_decode_median": base_dec,
        "baseline_prefill_median": base_pre,
        "points": len(recent),
    })
    return result


def build_report(entries, winner_tag=WINNER_TAG, baseline_tag=BASELINE_TAG):
    """Build the regression alert report dict from entries."""
    baseline = find_entry(entries, baseline_tag)
    winner = find_entry(entries, winner_tag)

    report = {
        "schema_version": 1,
        "winner_tag": winner_tag,
        "baseline_tag": baseline_tag,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "alert": False,
        "checks": {},
    }

    if not baseline:
        report["alert"] = True
        msg = f"Baseline tag '{baseline_tag}' not found in sweep summary"
        report["checks"]["baseline_found"] = {"passed": False, "message": msg}
        report["error"] = msg
    else:
        report["checks"]["baseline_found"] = {"passed": True, "message": "Baseline found"}

    if not winner:
        report["alert"] = True
        msg = f"Winner tag '{winner_tag}' not found in sweep summary"
        report["checks"]["winner_found"] = {"passed": False, "message": msg}
        report["error"] = msg
    else:
        report["checks"]["winner_found"] = {"passed": True, "message": "Winner found"}

    if not (baseline and winner):
        return report

    base_dec = baseline.get("decode_median", 0)
    base_pre = baseline.get("prefill_median", 0)
    win_dec = winner.get("decode_median", 0)
    win_pre = winner.get("prefill_median", 0)
    win_coh = winner.get("coherence_pass", False)

    dec_ratio = win_dec / base_dec if base_dec > 0 else 0.0
    pre_ratio = win_pre / base_pre if base_pre > 0 else 0.0

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

    decode_beats = win_dec > base_dec
    prefill_beats = win_pre > base_pre
    coherence_ok = bool(win_coh)

    report["checks"]["decode_beats_baseline"] = {
        "passed": decode_beats,
        "winner": win_dec,
        "baseline": base_dec,
        "ratio": dec_ratio,
        "message": (f"Winner decode {win_dec:.1f} > baseline {base_dec:.1f}"
                    if decode_beats
                    else f"FAIL: winner decode {win_dec:.1f} <= baseline {base_dec:.1f}"),
    }
    report["checks"]["prefill_beats_baseline"] = {
        "passed": prefill_beats,
        "winner": win_pre,
        "baseline": base_pre,
        "ratio": pre_ratio,
        "message": (f"Winner prefill {win_pre:.1f} > baseline {base_pre:.1f}"
                    if prefill_beats
                    else f"FAIL: winner prefill {win_pre:.1f} <= baseline {base_pre:.1f}"),
    }
    report["checks"]["winner_coherence"] = {
        "passed": coherence_ok,
        "message": "Winner coherence pass" if coherence_ok else "FAIL: winner coherence fail",
    }

    # Warm-repeat checks
    warm_winner = load_warm_median(winner_tag)
    warm_baseline = load_warm_median(baseline_tag)

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
            warm_dec_ratio = (warm_winner["decode_median"] / warm_baseline["decode_median"]
                              if warm_baseline["decode_median"] > 0 else 0.0)
            warm_pre_ratio = (warm_winner["prefill_median"] / warm_baseline["prefill_median"]
                              if warm_baseline["prefill_median"] > 0 else 0.0)
            report["metrics"]["winner_warm_improvement_pct"] = {
                "decode": (warm_dec_ratio - 1.0) * 100,
                "prefill": (warm_pre_ratio - 1.0) * 100,
            }

    if warm_baseline:
        report["metrics"]["baseline_warm"] = warm_baseline

    critical = [report["checks"][c]["passed"] for c in CRITICAL_CHECKS
                if c in report["checks"]]
    report["alert"] = not all(critical) if critical else False
    return report


def build_webhook_payload(report, drift=None):
    """Build a compact notification payload."""
    alert = report.get("alert", False)
    drift_detected = bool(drift and drift.get("drift_detected"))
    lines = []
    if alert:
        lines.append("ALERT: performance regression detected!")
    elif drift_detected:
        lines.append("WARNING: performance drift detected vs recent history.")
    else:
        lines.append("OK: no performance regression detected.")
    metrics = report.get("metrics", {})
    if metrics:
        w = metrics.get("winner", {})
        b = metrics.get("baseline", {})
        lines.append(f"Winner {report['winner_tag']}: decode={w.get('decode_median')} "
                     f"prefill={w.get('prefill_median')} tok/s")
        lines.append(f"Baseline {report['baseline_tag']}: decode={b.get('decode_median')} "
                     f"prefill={b.get('prefill_median')} tok/s")
    if drift and drift.get("drift_detected"):
        lines.append(f"Drift ratios: decode={drift.get('decode_ratio')} "
                     f"prefill={drift.get('prefill_ratio')} (threshold {drift.get('threshold')})")
    text = "\n".join(lines)
    return {"text": text, "alert": alert, "drift": drift_detected, "report": report}


def send_webhook(url, payload, dry_run=False, timeout=15):
    """Send a webhook notification. Returns (ok, message)."""
    data = json.dumps(payload).encode()
    if dry_run:
        return True, "dry-run: " + json.dumps(payload)
    try:
        req = urllib.request.Request(url, data=data, method="POST",
                                    headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"webhook sent (HTTP {resp.status})"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"webhook failed: {e}"


def main():
    ap = argparse.ArgumentParser(description="Emit performance regression alert metrics")
    ap.add_argument("--json-out", default="runs/regression-alert.json",
                    help="Path to write JSON report (default: runs/regression-alert.json)")
    ap.add_argument("--summary", default=None, help="Path to sweep-summary.jsonl")
    ap.add_argument("--history-file", default=str(HISTORY_FILE_DEFAULT),
                    help="Path to append alert history (default: runs/regression-alert-history.jsonl)")
    ap.add_argument("--no-history", action="store_true", help="Do not append to history file")
    ap.add_argument("--winner-tag", default=WINNER_TAG)
    ap.add_argument("--baseline-tag", default=BASELINE_TAG)
    ap.add_argument("--webhook-url", default=os.environ.get("STRATA_ALERT_WEBHOOK_URL") or
                    os.environ.get("STRATA_ALERT_WEBHOOK"),
                    help="Webhook URL for notifications (env: STRATA_ALERT_WEBHOOK_URL)")
    ap.add_argument("--drift-threshold", type=float, default=0.10,
                    help="Drift detection threshold (default: 0.10)")
    ap.add_argument("--drift-window", type=int, default=5,
                    help="Number of recent history entries for drift baseline (default: 5)")
    ap.add_argument("--strict-drift", action="store_true",
                    help="Exit non-zero on drift detection (default: report only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print webhook payload without sending")
    args = ap.parse_args()

    entries = load_entries(args.summary)
    report = build_report(entries, winner_tag=args.winner_tag,
                         baseline_tag=args.baseline_tag)

    # Drift detection against history (before appending current)
    history = load_history(args.history_file)
    drift = None
    metrics = report.get("metrics")
    if metrics:
        drift = detect_drift(
            history,
            metrics["winner"]["decode_median"],
            metrics["winner"]["prefill_median"],
            threshold=args.drift_threshold,
            window=args.drift_window,
        )
    report["drift"] = drift

    # Append to history (compact record)
    if not args.no_history and metrics:
        record = {
            "timestamp": report["timestamp"],
            "winner_tag": report["winner_tag"],
            "baseline_tag": report["baseline_tag"],
            "winner_decode": metrics["winner"]["decode_median"],
            "winner_prefill": metrics["winner"]["prefill_median"],
            "baseline_decode": metrics["baseline"]["decode_median"],
            "baseline_prefill": metrics["baseline"]["prefill_median"],
            "decode_ratio": metrics["ratios"]["decode"],
            "prefill_ratio": metrics["ratios"]["prefill"],
            "alert": report["alert"],
            "drift_detected": bool(drift and drift.get("drift_detected")),
        }
        try:
            append_history(record, args.history_file)
        except OSError as e:
            print(f"WARNING: could not append history: {e}", file=sys.stderr)

    # Webhook notification
    if args.webhook_url:
        payload = build_webhook_payload(report, drift)
        ok, msg = send_webhook(args.webhook_url, payload, dry_run=args.dry_run)
        report["webhook"] = {"ok": ok, "message": msg}
        if not ok:
            print(f"WARNING: {msg}", file=sys.stderr)
        else:
            print(msg)

    # Write JSON report
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    # Print summary
    print(json.dumps(report, indent=2))

    alert = report.get("alert", False)
    drift_detected = bool(drift and drift.get("drift_detected"))
    if alert:
        print("\nALERT: Performance regression detected!", file=sys.stderr)
        return 1
    if drift_detected and args.strict_drift:
        print("\nALERT: Performance drift detected!", file=sys.stderr)
        return 1
    if drift_detected:
        print("\nWARNING: Performance drift detected (report-only).", file=sys.stderr)
    else:
        print("\nNo performance regression detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
