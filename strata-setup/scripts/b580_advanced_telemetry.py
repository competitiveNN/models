#!/usr/bin/env python3
"""Advanced telemetry snapshot for dual-B580 Strata deployments.

Collects read-only host/GPU/service state for bottleneck diagnosis:
- Strata /health endpoint
- PCIe link width/speed and BDF topology from sysfs
- Intel i915/xe TDR/job_timeout_ms values
- NUMA, CPU affinity, render nodes
- Optional sycl-ls/lspci/clinfo summaries

The script degrades gracefully when tools/files are unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_HEALTH_URL = "http://127.0.0.1:1235/health"
DEFAULT_OUTPUT = "runs/b580_telemetry_snapshot.json"


def _run(cmd: list[str], timeout: float = 5.0) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        return {
            "cmd": cmd,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as e:  # noqa: BLE001
        return {"cmd": cmd, "ok": False, "error": str(e)}


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return None


def check_server_health(url: str, timeout: float) -> dict[str, Any]:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            return {"status": "healthy", "url": url, "details": payload}
    except Exception as e:  # noqa: BLE001
        return {"status": "unhealthy", "url": url, "error": str(e)}


def collect_render_nodes() -> dict[str, Any]:
    dri = Path("/dev/dri")
    nodes = sorted(p.name for p in dri.glob("renderD*")) if dri.exists() else []
    by_path = sorted(p.name for p in (dri / "by-path").glob("*")) if (dri / "by-path").exists() else []
    return {"render_nodes": nodes, "by_path": by_path}


def collect_pci_devices() -> dict[str, Any]:
    devices = []
    drm_cards = sorted(Path("/sys/class/drm").glob("card[0-9]*"))
    seen = set()
    for card in drm_cards:
        dev = card / "device"
        if not dev.exists():
            continue
        try:
            bdf = dev.resolve().name
        except Exception:  # noqa: BLE001
            bdf = dev.name
        if bdf in seen:
            continue
        seen.add(bdf)
        vendor = _read_text(dev / "vendor")
        device = _read_text(dev / "device")
        record = {
            "card": card.name,
            "bdf": bdf,
            "vendor": vendor,
            "device": device,
            "numa_node": _read_text(dev / "numa_node"),
            "current_link_speed": _read_text(dev / "current_link_speed"),
            "current_link_width": _read_text(dev / "current_link_width"),
            "max_link_speed": _read_text(dev / "max_link_speed"),
            "max_link_width": _read_text(dev / "max_link_width"),
            "driver": Path(dev / "driver").resolve().name if (dev / "driver").exists() else None,
        }
        # TDR/job timeout can appear under drm card gt/engines or device-level paths depending on driver/kernel.
        tdr_paths = []
        for pat in [card / "gt" / "gt*" / "engines" / "*" / "job_timeout_ms", card / "engine" / "*" / "job_timeout_ms"]:
            tdr_paths.extend(sorted(pat.parent.parent.glob(pat.relative_to(pat.parent.parent).as_posix())) if False else [])
        # Simpler globbing:
        for p in card.glob("gt/gt*/engines/*/job_timeout_ms"):
            tdr_paths.append(p)
        for p in card.glob("engine/*/job_timeout_ms"):
            tdr_paths.append(p)
        for p in dev.glob("drm/card*/gt/gt*/engines/*/job_timeout_ms"):
            tdr_paths.append(p)
        tdr = {}
        for p in sorted(set(tdr_paths)):
            val = _read_text(p)
            if val is not None:
                tdr[str(p)] = val
        record["job_timeout_ms"] = tdr
        devices.append(record)
    return {"pci_devices": devices}


def collect_numa_cpu() -> dict[str, Any]:
    data: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    affinity = None
    try:
        affinity = sorted(os.sched_getaffinity(0))
    except Exception:  # noqa: BLE001
        affinity = None
    data["sched_affinity"] = affinity
    numa_nodes = {}
    sys_nodes = Path("/sys/devices/system/node")
    if sys_nodes.exists():
        for node in sorted(sys_nodes.glob("node[0-9]*")):
            numa_nodes[node.name] = {
                "cpulist": _read_text(node / "cpulist"),
                "meminfo_present": (node / "meminfo").exists(),
            }
    data["numa_nodes"] = numa_nodes
    data["numactl_hardware"] = _run(["numactl", "--hardware"], timeout=5)
    data["lscpu"] = _run(["lscpu"], timeout=5)
    return data


def collect_tooling() -> dict[str, Any]:
    return {
        "lspci_b580": _run(["bash", "-lc", "lspci -nnk | grep -Ei 'B580|Battlemage|e20b|VGA compatible controller.*Intel' -A3"], timeout=5),
        "sycl_ls": _run(["sycl-ls"], timeout=5),
        "clinfo_platforms": _run(["bash", "-lc", "clinfo -l 2>/dev/null | head -n 40"], timeout=5),
        "intel_gpu_top_present": Path("/usr/bin/intel_gpu_top").exists() or Path("/usr/sbin/intel_gpu_top").exists(),
    }


def build_snapshot(health_url: str, timeout: float) -> dict[str, Any]:
    return {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "health": check_server_health(health_url, timeout),
        "host": collect_numa_cpu(),
        "render": collect_render_nodes(),
        "pci": collect_pci_devices(),
        "tooling": collect_tooling(),
        "notes": [
            "Read-only snapshot; missing tools/files are reported, not fatal.",
            "For 2xB580 PP=2, asymmetric PCIe x8/x4 and lack of L0 P2P are expected bottlenecks.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect dual-B580 Strata telemetry snapshot")
    ap.add_argument("--health-url", default=os.environ.get("STRATA_HEALTH_URL", DEFAULT_HEALTH_URL))
    ap.add_argument("--output", default=os.environ.get("STRATA_TELEMETRY_OUT", DEFAULT_OUTPUT))
    ap.add_argument("--timeout", type=float, default=5.0)
    args = ap.parse_args()

    snapshot = build_snapshot(args.health_url, args.timeout)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Telemetry snapshot saved to {out}")
    print(f"Health: {snapshot['health'].get('status')}; PCI devices: {len(snapshot['pci'].get('pci_devices', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
