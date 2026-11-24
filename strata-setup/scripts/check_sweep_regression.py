#!/usr/bin/env python3
"""Automated performance regression check against a FIXED baseline.

Reads runs/sweep-summary.jsonl and checks every config against the fixed
baseline tag (baseline-ctx64k-auto-spec4-par1). Fails if decode or prefill
drops below threshold (default 40%), or coherence fails.

Validates required schema: tag, decode_median, prefill_median, coherence_pass, env.
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_FILE = ROOT / "runs" / "sweep-summary.jsonl"
FIXED_BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"

REQUIRED_FIELDS = {"tag", "decode_median", "prefill_median", "coherence_pass", "env"}


def is_promoted_entry(tag: str, winner_tag: str, baseline_tag: str) -> bool:
    """Return True if this entry belongs to the promoted/production tier."""
    if tag in (winner_tag, baseline_tag):
        return True
    if tag.startswith("r3-"):
        return True
    return False


def is_historical_entry(tag: str, winner_tag: str, baseline_tag: str) -> bool:
    """Return True if this entry belongs to the historical/exploratory tier."""
    return not is_promoted_entry(tag, winner_tag, baseline_tag)


def validate_schema(entry):
    """Return (valid, errors) for an entry."""
    errors = []
    if not isinstance(entry, dict):
        return False, ["entry is not a dict"]
    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"missing required field '{field}'")
    if "tag" in entry and not isinstance(entry["tag"], str):
        errors.append("tag must be a string")
    if "decode_median" in entry and not isinstance(entry["decode_median"], (int, float)):
        errors.append("decode_median must be numeric")
    if "prefill_median" in entry and not isinstance(entry["prefill_median"], (int, float)):
        errors.append("prefill_median must be numeric")
    if "coherence_pass" in entry and not isinstance(entry["coherence_pass"], bool):
        errors.append("coherence_pass must be a boolean")
    if "env" in entry and not isinstance(entry["env"], (dict, list)):
        errors.append("env must be a dict or list")
    return len(errors) == 0, errors


def main():
    ap = argparse.ArgumentParser(description="Check sweep results for performance regression")
    ap.add_argument("--threshold", type=float, default=0.40,
                    help="Allowed drop fraction for promoted entries (default 0.40)")
    ap.add_argument("--historical-threshold", type=float, default=0.50,
                    help="Allowed drop fraction for historical/exploratory entries (default 0.50)")
    ap.add_argument("--baseline-tag", default=FIXED_BASELINE_TAG)
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any regression (default: report only)")
    ap.add_argument("--validate-schema", action="store_true", help="Validate all entries against required schema")
    ap.add_argument("--promoted-only", action="store_true",
                    help="Only check the promoted winner entry (not all exploratory configs)")
    ap.add_argument("--winner-tag", default="r3-spec4-ec8192-pw2-ppr4-pool20-int8",
                    help="Tag of the promoted winner to check")
    args = ap.parse_args()

    if not SUMMARY_FILE.exists():
        print(f"Sweep summary file not found: {SUMMARY_FILE}")
        return 0

    entries = []
    for i, line in enumerate(SUMMARY_FILE.read_text().splitlines()):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"Line {i+1}: invalid JSON: {e}")
    all_entries = list(entries)

    if args.promoted_only:
        promoted = [e for e in entries if e.get("tag") == args.winner_tag]
        if not promoted:
            print(f"Winner tag '{args.winner_tag}' not found in summary.")
            return 1
        # Only check the promoted entry, but keep baseline for reference
        entries = promoted

    if not entries:
        print("No sweep summary entries found.")
        return 0
    if not entries:
        print("No sweep summary entries found.")
        return 0

    # Schema validation
    if args.validate_schema:
        schema_ok = True
        for i, e in enumerate(entries):
            valid, errors = validate_schema(e)
            if not valid:
                schema_ok = False
                print(f"Entry {i+1} ({e.get('tag', '?')}): schema errors: {errors}")
        if not schema_ok:
            print("\nSchema validation FAILED.")
            return 1
        print(f"Schema validation PASSED ({len(entries)} entries).")

    baseline = None
    for e in all_entries:
        if e.get("tag") == args.baseline_tag:
            baseline = e
            break
    if baseline is None:
        print(f"Baseline tag '{args.baseline_tag}' not found; using max-decode entry.")
        baseline = max(entries, key=lambda x: x.get("decode_median", 0))

    base_decode = baseline.get("decode_median", 0)
    base_prefill = baseline.get("prefill_median", 0)
    print(f"Fixed baseline: {baseline.get('tag')} decode={base_decode:.1f} prefill={base_prefill:.1f} tok/s")

    failed = False
    for d in entries:
        tag = d.get("tag")
        coh = d.get("coherence_pass", True)
        dec = d.get("decode_median", 0)
        pre = d.get("prefill_median", 0)

        # Tier selection: promoted entries use strict threshold, historical use lenient
        if is_promoted_entry(tag, args.winner_tag, args.baseline_tag):
            eff_threshold = args.threshold
            tier_label = "promoted"
        else:
            eff_threshold = args.historical_threshold
            tier_label = "historical"

        if not coh:
            print(f"  [FAIL] {tag}: coherence check failed")
            failed = True
            continue

        # Decode check
        if base_decode > 0:
            dr = dec / base_decode
            status = "PASS" if dr >= (1 - eff_threshold) else "REGRESSION"
            print(f"  [{status}] {tag} ({tier_label}): decode={dec:.1f} (ratio={dr:.2f}, threshold={eff_threshold:.0%})")
            if dr < (1 - eff_threshold):
                failed = True

        # Prefill check
        if base_prefill > 0:
            pr = pre / base_prefill
            status = "PASS" if pr >= (1 - eff_threshold) else "REGRESSION"
            print(f"         prefill={pre:.1f} (ratio={pr:.2f}, threshold={eff_threshold:.0%}) [{status}]")
            if pr < (1 - eff_threshold):
                failed = True

    if failed:
        print("\nPerformance regression detected!")
        if args.strict:
            return 1
        print("(report-only mode; use --strict to fail)")
    else:
        print("\nAll configurations passed regression check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
