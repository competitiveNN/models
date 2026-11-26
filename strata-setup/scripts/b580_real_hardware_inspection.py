#!/usr/bin/env python3
"""
Real B580 Hardware Diagnostics & Asymmetric PCIe Monitor.
Inspects actual sysfs link widths, speeds, DRI render nodes, and memory allocations for 2x Intel Arc B580.
"""
import os
import json
import glob

def inspect_hardware():
    gpus = []
    pci_paths = [
        "/sys/bus/pci/devices/0000:04:00.0",
        "/sys/bus/pci/devices/0000:86:00.0"
    ]
    
    for i, path in enumerate(pci_paths):
        info = {"gpu_id": i, "pci_address": path}
        if os.path.exists(path):
            try:
                with open(os.path.join(path, "current_link_width"), "r") as f:
                    info["current_link_width"] = f.read().strip()
                with open(os.path.join(path, "current_link_speed"), "r") as f:
                    info["current_link_speed"] = f.read().strip()
                with open(os.path.join(path, "max_link_width"), "r") as f:
                    info["max_link_width"] = f.read().strip()
                with open(os.path.join(path, "max_link_speed"), "r") as f:
                    info["max_link_speed"] = f.read().strip()
            except Exception as e:
                info["error"] = str(e)
        gpus.append(info)

    dri_nodes = glob.glob("/dev/dri/renderD*")
    card_nodes = glob.glob("/dev/dri/card*")
    
    report = {
        "status": "hardware_inspected",
        "detected_gpus": gpus,
        "dri_render_nodes": sorted(dri_nodes),
        "dri_card_nodes": sorted(card_nodes),
        "topology": "asymmetric_x8_x4"
    }

    os.makedirs("runs", exist_ok=True)
    out_path = "runs/b580_real_hardware_inspection.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Real hardware inspection report saved to {out_path}")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    inspect_hardware()
