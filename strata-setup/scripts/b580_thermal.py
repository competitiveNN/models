#!/usr/bin/env python3
"""Real thermal monitoring for Intel Arc B580 GPUs via sysfs/hwmon.

Reads actual GPU temperature, power draw, and frequency from Linux kernel interfaces.
Exports to Prometheus format.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def read_thermal_data() -> dict[str, Any]:
    """Read thermal data from all hwmon devices for Intel GPUs."""
    hwmon_root = Path("/sys/class/hwmon")
    gpu_data = []
    
    for hwmon in sorted(hwmon_root.glob("hwmon*")):
        name_file = hwmon / "name"
        if not name_file.exists():
            continue
        try:
            name = name_file.read_text().strip()
        except Exception:
            continue
        
        # Intel GPU drivers typically expose as "i915" or "xe"
        if name not in ("i915", "xe", "intel_gpu"):
            continue
            
        gpu_info = {"name": name, "hwmon": hwmon.name}
        
        # Read temperature inputs
        for temp_file in sorted(hwmon.glob("temp*_input")):
            try:
                # Temperature is in millidegrees Celsius
                temp_mc = int(temp_file.read_text().strip())
                label_file = hwmon / temp_file.name.replace("_input", "_label")
                label = label_file.read_text().strip() if label_file.exists() else temp_file.name
                gpu_info[f"temp_{label}"] = temp_mc / 1000.0
            except Exception:
                pass
        
        # Read power inputs
        for power_file in sorted(hwmon.glob("power*_input")):
            try:
                # Power is in microwatts
                power_uw = int(power_file.read_text().strip())
                label_file = hwmon / power_file.name.replace("_input", "_label")
                label = label_file.read_text().strip() if label_file.exists() else power_file.name
                gpu_info[f"power_{label}"] = power_uw / 1_000_000.0
            except Exception:
                pass
        
        # Read frequency inputs
        for freq_file in sorted(hwmon.glob("freq*_input")):
            try:
                freq_hz = int(freq_file.read_text().strip())
                label_file = hwmon / freq_file.name.replace("_input", "_label")
                label = label_file.read_text().strip() if label_file.exists() else freq_file.name
                gpu_info[f"freq_{label}"] = freq_hz / 1_000_000_000.0  # GHz
            except Exception:
                pass
        
        if len(gpu_info) > 2:  # Has more than just name and hwmon
            gpu_data.append(gpu_info)
    
    return {"gpus": gpu_data, "count": len(gpu_data)}


def generate_prometheus_thermal(thermal_data: dict[str, Any]) -> str:
    """Generate Prometheus metrics from thermal data."""
    lines = [
        "# HELP strata_gpu_temperature_celsius GPU temperature in Celsius",
        "# TYPE strata_gpu_temperature_celsius gauge",
        "# HELP strata_gpu_power_watts GPU power draw in Watts",
        "# TYPE strata_gpu_power_watts gauge",
        "# HELP strata_gpu_frequency_ghz GPU frequency in GHz",
        "# TYPE strata_gpu_frequency_ghz gauge",
    ]
    
    for gpu in thermal_data.get("gpus", []):
        hwmon = gpu.get("hwmon", "unknown")
        for key, value in gpu.items():
            if key.startswith("temp_") and isinstance(value, (int, float)):
                label = key.replace("temp_", "")
                lines.append(f'strata_gpu_temperature_celsius{{hwmon="{hwmon}",sensor="{label}"}} {value}')
            elif key.startswith("power_") and isinstance(value, (int, float)):
                label = key.replace("power_", "")
                lines.append(f'strata_gpu_power_watts{{hwmon="{hwmon}",sensor="{label}"}} {value}')
            elif key.startswith("freq_") and isinstance(value, (int, float)):
                label = key.replace("freq_", "")
                lines.append(f'strata_gpu_frequency_ghz{{hwmon="{hwmon}",sensor="{label}"}} {value}')
    
    return "\n".join(lines) + "\n"


def main() -> int:
    data = read_thermal_data()
    if data["count"] == 0:
        print("# No Intel GPU thermal sensors found", file=sys.stderr)
        return 1
    print(generate_prometheus_thermal(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())