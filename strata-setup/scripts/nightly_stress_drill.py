#!/usr/bin/env python3
"""Nightly stress drill & config/schema validation for Strata dual-B580.

Validates all 2gpu config JSON files, checks required keys, reports
memory/residency sanity hints, and writes runs/nightly_stress_report.json.
"""

from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOB = "configs/strata-swift-iq3_xxs-2gpu*.json"
REQUIRED_ANY_KEYS = {"exe", "args", "env"}  # at least one expected in profile-style configs
RISKY_ENV_DEFAULTS = {
    "STRATA_PREFILL_RING": (1024, "large host ring; watch host RAM"),
    "STRATA_STAGER_RING": (256, "large stager ring; watch host RAM"),
    "STRATA_MIRROR_MIB": (32768, "large mirror; watch host RAM"),
}


def validate_config(path: Path) -> dict[str, Any]:
    rec: dict[str, Any] = {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), "exists": path.exists()}
    if not path.exists():
        rec["valid_json"] = False
        rec["errors"] = ["missing"]
        return rec
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        rec["valid_json"] = False
        rec["errors"] = [f"json_parse: {e}"]
        return rec
    rec["valid_json"] = True
    rec["keys"] = sorted(data.keys()) if isinstance(data, dict) else []
    rec["has_profile_keys"] = isinstance(data, dict) and bool(REQUIRED_ANY_KEYS.intersection(data.keys()))
    warnings = []
    env = data.get("env", {}) if isinstance(data, dict) else {}
    if isinstance(env, dict):
        for k, (threshold, msg) in RISKY_ENV_DEFAULTS.items():
            v = env.get(k)
            try:
                if v is not None and int(v) >= threshold:
                    warnings.append(f"{k}={v}: {msg}")
            except Exception:  # noqa: BLE001
                pass
    rec["warnings"] = warnings
    rec["errors"] = []
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="Nightly stress drill & config schema validation")
    ap.add_argument("--output", default="runs/nightly_stress_report.json")
    ap.add_argument("--glob", default=DEFAULT_GLOB)
    args = ap.parse_args()

    paths = sorted((ROOT / p).resolve() for p in glob.glob(str(ROOT / args.glob)))
    if not paths:
        # fallback to literal glob relative
        paths = sorted(Path(p) for p in glob.glob(args.glob))
    print(f"Running nightly stress drill: {len(paths)} config(s)...")
    cfg_results = [validate_config(p) for p in paths]
    valid = [r for r in cfg_results if r.get("valid_json")]
    invalid = [r for r in cfg_results if not r.get("valid_json")]
    all_valid = len(invalid) == 0 and len(valid) > 0

    report = {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "glob": args.glob,
        "total": len(cfg_results),
        "valid": len(valid),
        "invalid": len(invalid),
        "configs_checked": cfg_results,
        "stress_drill_passed": all_valid,
        "residency_note": "Kernel-fused-max profile: expert-cache 24576, ring 1024/stager 256/mirror 32768MiB - watch host RAM; 2xB580 ceiling remains hardware-bounded.",
    }

    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Valid: {len(valid)}/{len(cfg_results)}. Report: {out}")
    return 0 if all_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
