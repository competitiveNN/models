#!/usr/bin/env python3
"""Prometheus metrics exporter for 2x Intel Arc B580 Strata telemetry.

Exports GPU device presence, level-zero status, and basic telemetry to Prometheus format.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import b580_telemetry  # noqa: E402


def generate_prometheus_metrics() -> str:
    data = b580_telemetry.probe_telemetry()
    lines = [
        "# HELP strata_b580_device_present Intel Arc B580 device presence",
        "# TYPE strata_b580_device_present gauge",
    ]
    cards = data.get("sys_drm", [])
    for c in cards:
        lines.append(f'strata_b580_device_present{{card="{c.get("card")}",driver="{c.get("driver", "unknown")}"}} 1')

    lz = 1 if data.get("level_zero") else 0
    lines.extend([
        "# HELP strata_level_zero_available Level-Zero runtime availability",
        "# TYPE strata_level_zero_available gauge",
        f"strata_level_zero_available {lz}",
    ])
    return "\n".join(lines) + "\n"


def main():
    print(generate_prometheus_metrics(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
