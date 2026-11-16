#!/usr/bin/env python3
"""Generate a TDR-safe strata serve config for this rig.

The B580's xe driver kills any GPU job that runs longer than job_timeout_ms
(5 s, root-owned; see docs/tdr-mitigation.md). A config is "TDR-safe" when
every window is short enough to finish inside that budget:

  * more resident experts  -> fewer PCIe streams -> shorter windows
    (size --expert-cache to fill the free VRAM after the weights)
  * smaller --prefill chunk -> smaller prompt submissions
  * STRATA_VERIFY_STEPPED=1 -> per-layer segments, each a short GPU job

A 2-GPU layer split is currently NOT emittable: the cross-device hand-off
deadlocks at the first stage boundary on this build (see the plan doc). The tool
refuses to produce one unless --force is given.

Usage:
  tdr_safe_config.py [--template serve-1gpu-stepped.json] [--name NAME]
                     [--gpus N] [--free-vram-mib N] [--reserve-mib N]
                     [--slot-mib F] [--max-cache N] [--prefill N]
                     [--out PATH] [--print]

--free-vram-mib  free VRAM per card after the weights are loaded. If omitted the
                 tool probes `xpu-smi` and subtracts --weights-mib (default 4096,
                 the measured dense+head footprint for this pack on one card).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "strata-src"))
DEFAULT_SLOT_MIB = 1.7   # measured: ~1.66-1.7 MiB per expert slot on this pack


def probe_gpus():
    """Return (count, [total_vram_mib...]) using xpu-smi, or (0, [])."""
    exe = shutil.which("xpu-smi")
    if not exe:
        return 0, []
    try:
        out = subprocess.run([exe, "discovery"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return 0, []
    count = len(re.findall(r"Device Name:\s*Intel", out))
    # xpu-smi discovery does not report VRAM; assume the B580's 12 GiB per card.
    return count, [12288] * count


def probe_free_mib():
    """Best-effort current free VRAM (MiB) of card 0. xpu-smi does not expose it
    on this driver, so return None and let the caller estimate from total."""
    return None


def set_arg(args, flag, value):
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            args[i + 1] = str(value)
            return True
    args.extend([flag, str(value)])
    return False


def drop_arg(args, flag):
    out, i = [], 0
    while i < len(args):
        if args[i] == flag:
            i += 2 if i + 1 < len(args) and not args[i + 1].startswith("--") else 1
        else:
            out.append(args[i]); i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="serve-1gpu-stepped.json")
    ap.add_argument("--name", default="tdr-safe")
    ap.add_argument("--gpus", type=int, default=0)
    ap.add_argument("--free-vram-mib", type=int, default=0)
    ap.add_argument("--weights-mib", type=int, default=4096)
    ap.add_argument("--reserve-mib", type=int, default=1024)
    ap.add_argument("--slot-mib", type=float, default=DEFAULT_SLOT_MIB)
    ap.add_argument("--max-cache", type=int, default=3072)
    ap.add_argument("--prefill", type=int, default=32)
    ap.add_argument("--out", default="")
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    tpl = a.template if os.path.isabs(a.template) else os.path.join(SRC, a.template)
    if not os.path.exists(tpl):
        print(f"tdr_safe_config: template not found: {tpl}", file=sys.stderr)
        return 2
    cfg = json.load(open(tpl))
    args = list(cfg.get("args", []))

    gpus, totals = probe_gpus()
    detected = gpus
    if a.gpus:
        gpus = a.gpus
    else:
        # Default to a single card: it is the only configuration that serves on this
        # build. The physical GPU count is reported for information only.
        gpus = 1
    if detected and detected != gpus:
        print(f"tdr_safe_config: detected {detected} GPU(s); using {gpus} for the config")
    if detected == 0:
        print("tdr_safe_config: could not detect GPUs (xpu-smi missing?); assuming 1 GPU",
              file=sys.stderr)

    free = a.free_vram_mib or probe_free_mib()
    if not free:
        total = totals[0] if totals else 12288
        free = max(total - a.weights_mib, 0)
    budget_mib = max(free - a.reserve_mib, 0)
    slots = int(budget_mib / a.slot_mib)
    slots = max(0, min(slots, a.max_cache))

    cfg["model_name"] = a.name
    cfg["log"] = a.name + ".log"
    cfg.setdefault("env", {})

    if gpus >= 2:
        msg = (f"tdr_safe_config: refusing to emit a {gpus}-GPU layer-split config: the "
               "cross-device hand-off deadlocks on this build (see "
               "docs/tdr-mitigation.md). Re-run with --gpus 1 for a working "
               "single-card config, or --force to override.")
        if not a.force:
            print(msg, file=sys.stderr)
            return 3
        print("tdr_safe_config: WARNING: --force: 2-GPU split is known to hang", file=sys.stderr)
    else:
        # single card: keep an intra-GPU layer split (both stages on GPU0) so stepped
        # verify has a stage boundary to segment on; a single verifier runs one giant
        # window that exceeds the 5 s TDR. --split-device 0 pins both stages to GPU0.
        set_arg(args, "--layer-split", 47)
        set_arg(args, "--split-device", 0)
        cfg["env"]["STRATA_VERIFY_STEPPED"] = "1"
        cfg["env"].setdefault("STRATA_VERIFY_NO_HOST", "0")
        cfg["env"].setdefault("STRATA_WINDOW_SYNC", "1")
        cfg["env"].setdefault("ZE_FLAT_DEVICE_MEMORY", "1")
        cfg["env"]["ONEAPI_DEVICE_SELECTOR"] = "level_zero:0"
        cfg["env"].setdefault("STRATA_DEVICE_FILTER", "level_zero")

    set_arg(args, "--expert-cache", slots)
    set_arg(args, "--prefill", a.prefill)
    set_arg(args, "--pipeline-windows", 0)
    cfg["args"] = args

    out = a.out or os.path.join(SRC, a.name + ".json")
    with open(out, "w") as f:
        json.dump(cfg, f, indent=1)
    print(f"tdr_safe_config: wrote {out}")
    print(f"  gpus={gpus} free_vram={free} MiB reserve={a.reserve_mib} MiB "
          f"slot={a.slot_mib} MiB -> expert-cache={slots} slots "
          f"({slots*a.slot_mib/1024:.2f} GiB)")
    print(f"  prefill={a.prefill} stepped={'1' if cfg['env'].get('STRATA_VERIFY_STEPPED')=='1' else '0'}")
    if a.print:
        print(json.dumps(cfg, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())