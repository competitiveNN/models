#!/usr/bin/env python3
"""Collect a reproducible environment profile for Strata 2x B580 runs."""
import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_lspci_vga(output):
    """Parse `lspci` output for VGA/3D controllers."""
    devices = []
    for line in output.splitlines():
        low = line.lower()
        if "vga" in low or "3d" in low or "display" in low:
            devices.append(line.strip())
    return devices


def collect_profile():
    gpus = []
    try:
        r = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            gpus = parse_lspci_vga(r.stdout)
    except (OSError, subprocess.SubprocessError):
        gpus = []

    git_commit = None
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                           cwd=str(ROOT), timeout=10)
        if r.returncode == 0:
            git_commit = r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_commit = None

    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "git_commit": git_commit,
        "gpus": gpus,
    }


def main():
    ap = argparse.ArgumentParser(description="Collect environment profile")
    ap.add_argument("--output", default=None, help="Write JSON to this path")
    args = ap.parse_args()

    profile = collect_profile()
    text = json.dumps(profile, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
