#!/usr/bin/env python3
"""Replay failed webhook deliveries from a dead-letter file.

Reads a JSONL dead-letter file produced by regression_alert.py, retries each
delivery, and writes still-failed entries to an output file.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from regression_alert import send_webhook  # noqa: E402


def load_dead_letters(path):
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


def main():
    ap = argparse.ArgumentParser(description="Replay dead-lettered webhook deliveries")
    ap.add_argument("--input", required=True, help="Input dead-letter JSONL file")
    ap.add_argument("--output", default=None, help="Output file for still-failed entries")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records = load_dead_letters(args.input)
    if not records:
        print("No dead-letter records found.")
        return 0

    still_failed = []
    for rec in records:
        url = rec.get("url")
        payload = rec.get("payload", {})
        ok, msg = send_webhook(url, payload, dry_run=args.dry_run,
                               timeout=args.timeout, retries=args.retries)
        if ok:
            print(f"REPLAYED: {url}: {msg}")
        else:
            print(f"FAILED: {url}: {msg}", file=sys.stderr)
            still_failed.append(rec)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r) + "\n" for r in still_failed))
    print(f"Replayed {len(records)} record(s); {len(still_failed)} still failing.")
    return 1 if still_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
