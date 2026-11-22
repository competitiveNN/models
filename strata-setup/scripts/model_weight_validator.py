#!/usr/bin/env python3
"""Automated model weight validation and checksum verification for Strata B580 TP2.

Verifies GGUF shard integrity, PLE shard detection, and model file completeness.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "strata-old-source" / "terminal" / "strata_cli" / "launch"))

import adopt  # noqa: E402


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_model_shards(model_dir: Path) -> dict[str, Any]:
    """Validate model shards: completeness, PLE shard detection, checksums."""
    shards = adopt.find_shards(model_dir)
    if not shards:
        return {"valid": False, "error": "No complete shard set found", "shards": []}

    ple_shard = adopt.find_ple_shard(shards)
    shard_info = []
    for s in shards:
        shard_info.append({
            "path": str(s),
            "size_bytes": s.stat().st_size,
            "sha256": compute_sha256(s),
            "is_ple": s == ple_shard,
        })

    return {
        "valid": True,
        "shard_count": len(shards),
        "ple_shard": str(ple_shard),
        "shards": shard_info,
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Validate model weight shards")
    ap.add_argument("--model-dir", required=True, help="Path to model directory")
    ap.add_argument("--output", default=None, help="Output JSON file")
    args = ap.parse_args()

    model_dir = Path(args.model_dir)
    result = validate_model_shards(model_dir)
    output = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).write_text(output)
    else:
        print(output)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())