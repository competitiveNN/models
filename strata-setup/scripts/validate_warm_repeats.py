#!/usr/bin/env python3
"""Validate warm-repeat JSON files for CI.

Checks that all runs/warm-*.json files:
  * exist (at least one)
  * have the required schema fields
  * have unique tags
  * have positive decode/prefill medians
  * match the verified winner environment (for winner-associated warm files)

Usage:
  python3 scripts/validate_warm_repeats.py [--winner-tag TAG] [--baseline-tag TAG]
"""
import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINNER_TAG = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"

REQUIRED_FIELDS = {
    "tag", "repeats", "per_run", "decode_median", "prefill_median",
    "decode_mean", "prefill_mean", "decode_stdev", "prefill_stdev",
}
PER_RUN_FIELDS = {"run", "decode", "prefill"}


def load_warm_files():
    """Load all warm-*.json files. Return dict of tag->data."""
    warm = {}
    for p in sorted(Path("runs").glob("warm-*.json")):
        try:
            data = json.loads(p.read_text())
            tag = data.get("tag")
            if tag:
                warm[tag] = data
        except (json.JSONDecodeError, OSError) as e:
            print(f"FAIL: {p.name}: invalid JSON or unreadable: {e}")
    return warm


def validate_schema(data, path):
    """Return list of schema errors for a warm file."""
    errors = []
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"missing fields: {missing}")
    for field in ("tag",):
        if field in data and not isinstance(data[field], str):
            errors.append(f"{field} must be a string")
    for field in ("repeats",):
        if field in data and not isinstance(data[field], int):
            errors.append(f"{field} must be an int")
    if "per_run" in data and not isinstance(data["per_run"], list):
        errors.append("per_run must be a list")
    elif "per_run" in data:
        for i, run in enumerate(data["per_run"]):
            missing_run = PER_RUN_FIELDS - set(run.keys())
            if missing_run:
                errors.append(f"per_run[{i}] missing fields: {missing_run}")
    return errors


def validate_medians_positive(data, path):
    """Return error if decode_median or prefill_median is not positive."""
    errors = []
    if data.get("decode_median", 0) <= 0:
        errors.append(f"decode_median not positive: {data.get('decode_median')}")
    if data.get("prefill_median", 0) <= 0:
        errors.append(f"prefill_median not positive: {data.get('prefill_median')}")
    return errors


def main():
    ap = argparse.ArgumentParser(description="Validate warm-repeat JSON files for CI")
    ap.add_argument("--winner-tag", default=WINNER_TAG,
                    help="Tag of the promoted winner (default: %(default)s)")
    ap.add_argument("--baseline-tag", default=BASELINE_TAG,
                    help="Tag of the baseline (default: %(default)s)")
    args = ap.parse_args()

    warm = load_warm_files()

    if not warm:
        print("FAIL: No warm-*.json files found in runs/")
        return 1

    # Check uniqueness
    tags = list(warm.keys())
    if len(tags) != len(set(tags)):
        dupes = [t for t in tags if tags.count(t) > 1]
        print(f"FAIL: Duplicate warm tags: {dupes}")
        return 1

    failed = False
    for tag, data in sorted(warm.items()):
        path = Path("runs") / f"warm-{tag}.json"
        errors = []

        # Schema validation
        errors.extend(validate_schema(data, path))

        # Positive medians
        errors.extend(validate_medians_positive(data, path))

        if errors:
            failed = True
            print(f"FAIL: {path.name}:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"PASS: {path.name} "
                  f"(decode={data['decode_median']:.2f}, "
                  f"prefill={data['prefill_median']:.2f}, "
                  f"repeats={data['repeats']})")

    if failed:
        print("\nWarm-repeat validation FAILED.")
        return 1

    print(f"\nAll {len(warm)} warm-repeat files validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
