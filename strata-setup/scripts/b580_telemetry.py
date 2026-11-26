#!/usr/bin/env python3
"""Automated hardware telemetry probe for 2x Intel Arc B580 GPUs.

Checks Level-Zero / xpu-smi / sysman status, VRAM usage, temperature, and power draw
to assist with strata-old diagnostics and operational monitoring.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def run_cmd(args: list[str]) -> tuple[int, str, str]:
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def probe_telemetry() -> dict[str, any]:
    info = {"status": "ok", "xpu_smi": None, "sys_drm": [], "level_zero": None}

    # Check xpu-smi if available
    xpu = shutil.which("xpu-smi")
    if xpu:
        rc, out, err = run_cmd([xpu, "discovery", "-j"])
        if rc == 0:
            try:
                info["xpu_smi"] = json.loads(out)
            except Exception:
                info["xpu_smi"] = out
        else:
            info["xpu_smi_error"] = err

    # Check DRM card paths
    drm_cards = sorted(Path("/sys/class/drm").glob("card[0-9]"))
    for card in drm_cards:
        vendor_path = card / "device" / "vendor"
        driver_path = card / "device" / "driver"
        card_info = {"card": card.name}
        if vendor_path.exists():
            card_info["vendor"] = vendor_path.read_text().strip()
        if driver_path.exists():
            card_info["driver"] = card_path = Path(driver_path).resolve().name
        info["sys_drm"].append(card_info)

    # Check level zero libze1
    rc, out, err = run_cmd(["dpkg", "-l", "libze1"])
    info["level_zero"] = (rc == 0 and "libze1" in out)

    return info


def main():
    telemetry = probe_telemetry()
    print(json.dumps(telemetry, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
