#!/usr/bin/env python3
"""Validate the 2x Intel Arc B580 Strata configs for required tuning keys.

Checks required CLI args and expected runtime env values for the dual-GPU configs.
Exit 1 if any checked config fails; 0 otherwise.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"

CHECKED = [
    "strata-swift-iq3_xxs-2gpu-clean.json",
    "strata-swift-iq3_xxs-2gpu-optimized.json",
    "strata-swift-iq3_xxs-2gpu-miss108.json",
    "strata-edge-fixed.json",
    "strata-swift-iq3_xxs-2gpu-autov512.json",
]

REQUIRED_ARGS = ["--expert-cache", "--prefill", "--vram-reserve-mib", "--pipeline-windows", "--pool-workers", "--kv"]

def check_config(path: Path) -> tuple[bool, list[str]]:
    errors = []
    try:
        d = json.loads(path.read_text())
    except Exception as e:
        return False, [f"invalid JSON: {e}"]
    args = d.get("args") or []
    present = {a for a, _ in ((args[i], args[i+1]) for i in range(len(args)-1)) if a in REQUIRED_ARGS}
    for a in REQUIRED_ARGS:
        if a not in present:
            errors.append(f"missing required arg {a}")
    env = d.get("env") or {}
    expected_env = {
        "STRATA_PREFILL_MMQ": "0", "STRATA_WINDOW_SYNC": "1",
        "STRATA_VERIFY_DEVICE_PLAN": "0", "STRATA_VERIFY_NO_HOST": "0",
        "IGC_EnableGEPSimplification": "0", "SYCL_CACHE_PERSISTENT": "1",
    }
    for k, v in expected_env.items():
        if k not in env:
            errors.append(f"missing env {k}")
    return (len(errors) == 0), errors

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs-dir", default=str(CONFIGS))
    ap.add_argument("--only", nargs="*", default=CHECKED)
    args = ap.parse_args()
    cfg_dir = Path(args.configs_dir)
    failed = 0
    checked = 0
    for name in args.only:
        p = cfg_dir / name
        ok, errs = check_config(p)
        checked += 1
        if not ok:
            failed += 1
            print(f"❌ {name}: {errs}")
    print(f"Checked {checked} config file(s), {failed} failed.")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
