#!/usr/bin/env python3
"""
Fetch currently available free models from Kilo Code and OpenCode APIs.

Usage:
    python fetch-free-models.py --table
    python fetch-free-models.py --json --save free-models.json
    python fetch-free-models.py --csv --save free-models.csv
    python fetch-free-models.py --kilocode-only --table
    python fetch-free-models.py --opencode-only --json
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Configuration ──────────────────────────────────────────────────────────────
KILO_ENDPOINT = "https://api.kilo.ai/api/gateway/v1/models"
OPENCODE_ENDPOINT = "https://opencode.ai/zen/v1/models"
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 2

HEADERS = {
    "User-Agent": "fetch-free-models/1.0 (+https://github.com/defnlnotme/models)",
    "Accept": "application/json",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def fetch_json(url: str, attempt: int = 1) -> dict[str, Any] | list[Any] | None:
    """Fetch JSON with retry on 429/5xx and timeout handling."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and attempt <= MAX_RETRIES:
            retry_after = int(e.headers.get("Retry-After", str(BACKOFF_BASE ** attempt)))
            print(f"Rate limited (429), waiting {retry_after}s... (attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
            time.sleep(retry_after)
            return fetch_json(url, attempt + 1)
        if 500 <= e.code < 600 and attempt <= MAX_RETRIES:
            wait = BACKOFF_BASE ** attempt
            print(f"Server error {e.code}, retrying in {wait}s... (attempt {attempt}/{MAX_RETRIES})", file=sys.stderr)
            time.sleep(wait)
            return fetch_json(url, attempt + 1)
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Check auth credentials", file=sys.stderr)
        elif e.code == 403:
            print("Access forbidden — check permissions", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
    except TimeoutError:
        print(f"Request timed out after {TIMEOUT}s", file=sys.stderr)
    return None


def normalize_kilo(model: dict[str, Any]) -> dict[str, Any] | None:
    """Convert Kilo model format to common schema."""
    pricing = model.get("pricing", {})
    # Kilo uses string prices, convert to float
    def to_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    return {
        "id": model.get("id"),
        "name": model.get("name"),
        "provider": "kilocode",
        "context_length": model.get("context_length", 0),
        "pricing": {
            "input": to_float(pricing.get("prompt", 0)),
            "output": to_float(pricing.get("completion", 0)),
            "cache_read": to_float(pricing.get("input_cache_read", 0)),
            "cache_write": to_float(pricing.get("input_cache_write", 0)),
        },
        "capabilities": {
            "reasoning": "reasoning" in model.get("supported_parameters", []),
            "tool_call": "tools" in model.get("supported_parameters", []),
            "vision": "image" in model.get("architecture", {}).get("input_modalities", []),
            "open_weights": False,  # Kilo doesn't expose this
        },
        "source": "kilocode",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": model,
    }


def normalize_opencode(model_id: str) -> dict[str, Any] | None:
    """Convert OpenCode model format to common schema."""
    return {
        "id": model_id,
        "name": model_id,
        "provider": "opencode",
        "context_length": 0,
        "pricing": {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
        },
        "capabilities": {
            "reasoning": False,
            "tool_call": True,
            "vision": False,
            "open_weights": False,
        },
        "source": "opencode",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw": {"id": model_id},
    }


# ── Fetchers ───────────────────────────────────────────────────────────────────
def fetch_kilo() -> list[dict[str, Any]]:
    """Fetch and normalize free models from Kilo API."""
    print("Fetching from Kilo Code API...", file=sys.stderr)
    data = fetch_json(KILO_ENDPOINT)
    if not data or not isinstance(data, dict) or "data" not in data:
        print("Kilo: no data or unexpected format", file=sys.stderr)
        return []

    free_models = []
    for model in data["data"]:
        if model.get("isFree") is True:
            normalized = normalize_kilo(model)
            if normalized:
                free_models.append(normalized)

    print(f"Kilo: found {len(free_models)} free models", file=sys.stderr)
    return free_models


def fetch_opencode() -> list[dict[str, Any]]:
    """Fetch and normalize free models from OpenCode API."""
    print("Fetching from OpenCode API...", file=sys.stderr)
    data = fetch_json(OPENCODE_ENDPOINT)
    if not data or not isinstance(data, dict) or "data" not in data:
        print("OpenCode: no data or unexpected format", file=sys.stderr)
        return []

    free_models = []
    for model in data["data"]:
        model_id = model.get("id")
        if model_id:
            normalized = normalize_opencode(model_id)
            if normalized:
                free_models.append(normalized)

    print(f"OpenCode: found {len(free_models)} free models", file=sys.stderr)
    return free_models


# ── Output ─────────────────────────────────────────────────────────────────────
def output_json(data: list[dict], path: str | None):
    out = json.dumps(data, indent=2)
    if path:
        Path(path).write_text(out)
        print(f"Saved {len(data)} records to {path}", file=sys.stderr)
    else:
        print(out)


def output_csv(data: list[dict], path: str | None):
    if not data:
        return

    flat = []
    for d in data:
        caps = d.get("capabilities", {})
        pricing = d.get("pricing", {})
        row = {
            "id": d.get("id"),
            "name": d.get("name"),
            "provider": d.get("provider"),
            "context_length": d.get("context_length"),
            "pricing_input": pricing.get("input"),
            "pricing_output": pricing.get("output"),
            "pricing_cache_read": pricing.get("cache_read"),
            "pricing_cache_write": pricing.get("cache_write"),
            "reasoning": caps.get("reasoning"),
            "tool_call": caps.get("tool_call"),
            "vision": caps.get("vision"),
            "open_weights": caps.get("open_weights"),
            "source": d.get("source"),
            "fetched_at": d.get("fetched_at"),
        }
        flat.append(row)

    fieldnames = list(flat[0].keys())
    out_io = sys.stdout if path is None else open(path, "w", newline="")
    try:
        writer = csv.DictWriter(out_io, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat)
        if path:
            print(f"Saved {len(data)} records to {path}", file=sys.stderr)
    finally:
        if path:
            out_io.close()


def output_table(data: list[dict]):
    if not data:
        print("No records")
        return

    cols = [
        ("id", 50),
        ("name", 30),
        ("provider", 12),
        ("ctx", 8),
        ("$in", 8),
        ("$out", 8),
        ("reason", 6),
        ("tools", 5),
        ("vision", 6),
        ("open", 4),
    ]

    header = " | ".join(f"{name:<{w}}" for name, w in cols)
    print(header)
    print("-" * len(header))

    for d in data:
        caps = d.get("capabilities", {})
        pricing = d.get("pricing", {})
        row = [
            d.get("id", "")[:50],
            d.get("name", "")[:30],
            d.get("provider", "")[:12],
            str(d.get("context_length", 0)),
            f"{pricing.get('input', 0):.4f}",
            f"{pricing.get('output', 0):.4f}",
            "Y" if caps.get("reasoning") else "N",
            "Y" if caps.get("tool_call") else "N",
            "Y" if caps.get("vision") else "N",
            "Y" if caps.get("open_weights") else "N",
        ]
        print(" | ".join(f"{v:<{w}}" for (_, w), v in zip(cols, row)))


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fetch free models from Kilo Code and OpenCode APIs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    parser.add_argument("--table", action="store_true", help="Output as table (default)")
    parser.add_argument("--save", metavar="FILE", help="Save output to file instead of stdout")
    parser.add_argument("--kilocode-only", action="store_true", help="Only fetch from Kilo Code API")
    parser.add_argument("--opencode-only", action="store_true", help="Only fetch from OpenCode API")
    args = parser.parse_args()

    # Default to table if no format specified
    if not (args.json or args.csv or args.table):
        args.table = True

    # Validate mutually exclusive flags
    if args.kilocode_only and args.opencode_only:
        print("Error: --kilocode-only and --opencode-only are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    # Fetch data
    all_models = []

    if not args.opencode_only:
        kilo_models = fetch_kilo()
        all_models.extend(kilo_models)

    if not args.kilocode_only:
        opencode_models = fetch_opencode()
        all_models.extend(opencode_models)

    if not all_models:
        print("No free models found", file=sys.stderr)
        sys.exit(1)

    print(f"Total free models: {len(all_models)}", file=sys.stderr)

    # Output
    if args.json:
        output_json(all_models, args.save)
    elif args.csv:
        output_csv(all_models, args.save)
    else:
        output_table(all_models)


if __name__ == "__main__":
    main()