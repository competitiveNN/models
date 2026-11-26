#!/usr/bin/env python3
"""Audit STRATA_* env flags used by launch scripts/configs against engine source trees.

This prevents "no-op flag" drift: flags are classified as verified-in-source,
unverified, or absent. It does not prove runtime effectiveness, only source presence.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIRS = ["strata-src", "strata-src-clean", "strata-src-main"]
FLAG_RE = re.compile(r"\bSTRATA_[A-Z0-9_]+\b")
# Build/artifact dirs are noisy and slow; source-of-truth is .cpp/.h/.hpp/.py/.sh/.cmake
GREP_EXCLUDES = [
    "--exclude-dir=build*",
    "--exclude-dir=.git",
    "--exclude-dir=__pycache__",
    "--exclude-dir=.pytest_cache",
    "--exclude-dir=ggml",
    "--exclude-dir=llama.cpp",
]


def collect_flags(paths: list[Path]) -> set[str]:
    flags: set[str] = set()
    for p in paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        flags.update(FLAG_RE.findall(text))
    return flags


def grep_count(flag: str, source_dirs: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in source_dirs:
        if not d.exists():
            counts[str(d)] = 0
            continue
        cmd = [
            "grep",
            "-rl",
            "--include=*.cpp",
            "--include=*.h",
            "--include=*.hpp",
            "--include=*.py",
            "--include=*.sh",
            "--include=*.cmake",
            *GREP_EXCLUDES,
            flag,
            str(d),
        ]
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=30)
        files = [line for line in proc.stdout.splitlines() if line.strip()]
        counts[str(d)] = len(files)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="runs/env-flag-audit.json")
    ap.add_argument("--sources", nargs="*", default=DEFAULT_SOURCE_DIRS)
    ap.add_argument(
        "--inputs",
        nargs="*",
        default=[
            "run-strata-2gpu.sh",
            "run-strata-4gpu.sh",
            "configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json",
            "configs/strata-swift-iq3_xxs-2gpu-ultimate.json",
            "scripts/strata_regression_audit.py",
        ],
    )
    ap.add_argument("--strict", action="store_true", help="Exit 2 if any flags absent from source")
    args = ap.parse_args()

    input_paths = [ROOT / p for p in args.inputs]
    flags = sorted(collect_flags(input_paths))
    source_dirs = [ROOT / s for s in args.sources]

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": args.inputs,
        "sources": args.sources,
        "flags": {},
        "summary": {"verified_in_source": 0, "absent_from_source": 0, "total_flags": len(flags)},
    }
    for flag in flags:
        counts = grep_count(flag, source_dirs)
        total = sum(counts.values())
        status = "verified_in_source" if total > 0 else "absent_from_source"
        report["flags"][flag] = {"status": status, "file_count_by_source": counts, "total_files": total}
        report["summary"][status] += 1

    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote {out}")
    if args.strict and report["summary"]["absent_from_source"]:
        return 2
    return 0


if __name__ == "__main__":
    import time
    raise SystemExit(main())
