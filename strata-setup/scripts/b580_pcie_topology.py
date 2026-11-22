#!/usr/bin/env python3
"""PCIe topology and bus-speed diagnostic helper for 2x Intel Arc B580 GPUs."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def probe_pcie() -> dict:
    devices = []
    drm_root = Path("/sys/class/drm")
    # Only render nodes are GPU devices; display connectors (DP/HDMI) are child nodes.
    cards = sorted(drm_root.glob("renderD*"))
    for card in cards:
        try:
            device = card / "device"
            pnp = device / "pnp"
            seg = device / "segment"
            bus = device / "bus"
            speed_file = device / "speed"
            numa = device / "numa_node"
            info = {
                "card": card.name,
                "pnp_id": pnp.read_text().strip() if pnp.exists() else None,
                "segment": seg.read_text().strip() if seg.exists() else None,
                "bus": bus.read_text().strip() if bus.exists() else None,
                "speed": speed_file.read_text().strip() if speed_file.exists() else None,
                "numa": numa.read_text().strip() if numa.exists() else None,
            }
            devices.append(info)
        except Exception as e:
            devices.append({"card": card.name, "error": str(e)})
    return {"devices": devices, "count": len(devices)}


def main():
    data = probe_pcie()
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
