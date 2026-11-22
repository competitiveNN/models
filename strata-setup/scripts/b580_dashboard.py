#!/usr/bin/env python3
"""Generate a simple static dashboard summary for the 2x B580 TP2 Strata setup.

Combines benchmark results and telemetry into a compact markdown dashboard.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


def generate_dashboard(bench_path: Path | None = None, telemetry_path: Path | None = None) -> str:
    bench_file = bench_path or (RUNS / "bench-results.json")
    telemetry_file = telemetry_path or (RUNS / "metrics.prom")
    data: dict = {}
    if bench_file.exists():
        data = json.loads(bench_file.read_text())
    telemetry_lines: list[str] = []
    if telemetry_file.exists():
        telemetry_lines = telemetry_file.read_text().splitlines()

    lines = ["# Strata 2x B580 TP2 Dashboard", ""]
    if "benchmarks" in data:
        for name, bm in data.get("benchmarks", {}).items():
            r = bm.get("results") or {}
            lines.append(f"- {name}: throughput={r.get('throughput_median', 0):.1f} tok/s, latency={r.get('latency_median', 0.0):.2f}s")
    lines.append("")
    lines.append("## Telemetry")
    lines.extend([l for l in telemetry_lines if l.startswith("strata_")])

    return "\n".join(lines) + "\n"


def main() -> int:
    print(generate_dashboard())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
