#!/usr/bin/env python3
"""Export the verified winner configuration as a canonical JSON document."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_deployed_defaults import (  # noqa: E402
    SHELL_VARS, parse_shell_defaults, load_entries, find_entry, WINNER_TAG,
    BASELINE_TAG, load_warm_repeats, warm_median,
)

SUMMARY = ROOT / "runs" / "sweep-summary.jsonl"
SCRIPT = ROOT / "run-strata-2gpu.sh"


def main():
    ap = argparse.ArgumentParser(description="Export verified winner configuration")
    ap.add_argument("--output", default=None, help="Write JSON to this path")
    args = ap.parse_args()

    if not SCRIPT.exists() or not SUMMARY.exists():
        print("ERROR: required inputs missing", file=sys.stderr)
        return 1

    script_text = SCRIPT.read_text()
    defaults = parse_shell_defaults(script_text)
    entries = load_entries()
    winner = find_entry(WINNER_TAG)
    baseline = find_entry(BASELINE_TAG)
    if winner is None:
        print("ERROR: winner not found", file=sys.stderr)
        return 1

    warm_data = load_warm_repeats()
    warm = warm_median(WINNER_TAG, warm_data)

    doc = {
        "winner_tag": WINNER_TAG,
        "baseline_tag": BASELINE_TAG,
        "shell_defaults": {v: defaults.get(v) for v in SHELL_VARS},
        "winner_env": winner.get("env", {}),
        "winner_throughput": {
            "decode_median": winner.get("decode_median"),
            "prefill_median": winner.get("prefill_median"),
            "coherence_pass": winner.get("coherence_pass"),
        },
        "baseline_throughput": {
            "decode_median": baseline.get("decode_median") if baseline else None,
            "prefill_median": baseline.get("prefill_median") if baseline else None,
        },
        "warm_repeat": warm,
        "provenance": winner.get("provenance"),
    }

    text = json.dumps(doc, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
