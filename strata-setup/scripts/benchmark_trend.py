#!/usr/bin/env python3
"""Automated benchmark trend tracker with historical data storage.

Tracks benchmark throughput over time and detects long-term regressions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any


class BenchmarkTrendTracker:
    def __init__(self, history_file: Path | None = None):
        self.history_file = history_file or Path(__file__).resolve().parents[1] / "runs" / "benchmark_history.json"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def load_history(self) -> list[dict[str, Any]]:
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text())
            except Exception:
                return []
        return []

    def save_history(self, history: list[dict[str, Any]]) -> None:
        self.history_file.write_text(json.dumps(history, indent=2))

    def add_run(self, bench_results: dict[str, Any]) -> None:
        history = self.load_history()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "benchmarks": bench_results.get("benchmarks", {}),
            "url": bench_results.get("url", ""),
        }
        history.append(entry)
        self.save_history(history)

    def get_trend(self, benchmark_name: str, metric: str = "throughput_median", last_n: int = 20) -> list[dict[str, Any]]:
        history = self.load_history()
        trend = []
        for entry in history[-last_n:]:
            bm = entry.get("benchmarks", {}).get(benchmark_name, {})
            r = bm.get("results", {})
            if metric in r:
                trend.append({
                    "timestamp": entry["timestamp"],
                    "value": r[metric],
                })
        return trend

    def detect_regression(self, benchmark_name: str, metric: str = "throughput_median", threshold: float = 0.15) -> dict[str, Any]:
        trend = self.get_trend(benchmark_name, metric)
        if len(trend) < 2:
            return {"status": "insufficient_data", "points": len(trend)}
        
        recent = trend[-1]["value"]
        baseline = trend[0]["value"]
        if baseline == 0:
            return {"status": "no_baseline"}
        
        ratio = recent / baseline
        is_regression = ratio < (1 - threshold)
        
        return {
            "status": "regression" if is_regression else "ok",
            "recent": recent,
            "baseline": baseline,
            "ratio": round(ratio, 3),
            "threshold": threshold,
            "points": len(trend),
        }

    def generate_report(self) -> str:
        history = self.load_history()
        if not history:
            return "No benchmark history available."
        
        latest = history[-1]
        lines = [
            "# Benchmark Trend Report",
            f"Generated: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            f"Total runs: {len(history)}",
            "",
            "## Latest Run ({})".format(latest["timestamp"]),
        ]
        
        for name, bm in latest.get("benchmarks", {}).items():
            r = bm.get("results", {})
            trend = self.detect_regression(name)
            status = "🔴 REGRESSION" if trend["status"] == "regression" else "🟢 OK"
            lines.append(f"- {name}: throughput={r.get('throughput_median', 0):.1f} tok/s, latency={r.get('latency_median', 0):.2f}s [{status}]")
            if trend["status"] == "regression":
                lines.append(f"  → Dropped from {trend['baseline']:.1f} to {trend['recent']:.1f} tok/s ({trend['ratio']:.2f}x)")
        
        return "\n".join(lines)


def main() -> int:
    tracker = BenchmarkTrendTracker()
    report = tracker.generate_report()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())