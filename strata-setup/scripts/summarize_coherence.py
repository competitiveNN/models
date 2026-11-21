#!/usr/bin/env python3
"""Summarize coherence and degenerate output rates across historical benchmark JSONs."""
from __future__ import annotations
import json, glob
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from coherence import is_degenerate_response

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-rate", type=float, default=0.0, help="Minimum coherence rate [0-1]; exit 1 if below")
    args = ap.parse_args()

    json_files = sorted(glob.glob(str(ROOT / "runs" / "bench-containers-*.json")))
    total_requests = 0
    degenerate_requests = 0
    for jf in json_files:
        try:
            d = json.load(open(jf, encoding="utf-8"))
            for img, res in d.get("images", {}).items():
                for r in res.get("results", []):
                    total_requests += 1
                    # check content preview or error
                    preview = {"content": r.get("content_preview")}
                    if is_degenerate_response(preview) or r.get("degenerate"):
                        degenerate_requests += 1
        except Exception:
            pass
    rate = 100.0 * (1 - degenerate_requests / total_requests) if total_requests > 0 else 100.0
    print(f"=== Coherence Summary ===")
    print(f"Analyzed {len(json_files)} benchmark artifacts.")
    print(f"Total benchmark requests: {total_requests}")
    print(f"Degenerate / gibberish outputs: {degenerate_requests}")
    print(f"Coherence rate: {rate:.2f}%")
    if args.min_rate > 0 and rate < 100.0 * args.min_rate:
        print(f"FAIL: coherence rate {rate:.2f}% below threshold {args.min_rate*100:.0f}%", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
