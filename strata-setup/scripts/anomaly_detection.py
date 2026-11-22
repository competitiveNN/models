#!/usr/bin/env python3
"""Statistical anomaly detection for Strata B580 TP2 telemetry metrics.

Implements simple statistical anomaly detection (Z-score, IQR, rolling statistics)
for detecting anomalies in GPU temperature, throughput, latency, and power metrics.
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field


@dataclass
class AnomalyResult:
    metric: str
    value: float
    mean: float
    std: float
    z_score: float
    is_anomaly: bool
    threshold: float
    severity: str


class RollingAnomalyDetector:
    def __init__(self, window_size: int = 100, z_threshold: float = 3.0):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.values: dict[str, deque] = {}

    def add_value(self, metric: str, value: float) -> AnomalyResult | None:
        if metric not in self.values:
            self.values[metric] = deque(maxlen=self.window_size)

        self.values[metric].append(value)

        if len(self.values[metric]) < 10:
            return None

        vals = list(self.values[metric])
        mean = sum(vals) / len(vals)
        variance = sum((x - mean) ** 2 for x in vals) / len(vals)
        std = variance ** 0.5 if variance > 0 else 0.0

        if std == 0:
            z_score = 0.0
        else:
            z_score = abs(value - mean) / std

        is_anomaly = z_score > self.z_threshold
        severity = "critical" if z_score > 4.0 else ("warning" if is_anomaly else "normal")

        return AnomalyResult(
            metric=metric,
            value=value,
            mean=mean,
            std=std,
            z_score=z_score,
            is_anomaly=is_anomaly,
            threshold=self.z_threshold,
            severity=severity,
        )


def detect_iqr_anomalies(values: list[float], multiplier: float = 1.5) -> list[float]:
    """Detect anomalies using Interquartile Range (IQR) method."""
    if len(values) < 4:
        return []
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[3 * n // 4]
    iqr = q3 - q1
    lower_bound = q1 - multiplier * iqr
    upper_bound = q3 + multiplier * iqr
    return [v for v in values if v < lower_bound or v > upper_bound]


def main() -> int:
    detector = RollingAnomalyDetector(window_size=50, z_threshold=2.5)
    
    # Simulate some normal and anomalous values
    normal_vals = [10.0, 10.2, 9.8, 10.1, 10.3, 9.9, 10.0, 10.2, 9.8, 10.1] * 5
    anomalous_vals = [10.0, 10.2, 50.0, 10.1, 10.3, 9.9, 10.0, 10.2, 9.8, 10.1] * 5
    
    print("=== Normal values ===")
    for v in normal_vals:
        result = detector.add_value("test_metric", v)
        if result and result.is_anomaly:
            print(f"  ANOMALY: {result.metric}={result.value:.2f}, z={result.z_score:.2f}")
    
    print("\n=== Anomalous values ===")
    for v in anomalous_vals:
        result = detector.add_value("test_metric", v)
        if result and result.is_anomaly:
            print(f"  ANOMALY: {result.metric}={result.value:.2f}, z={result.z_score:.2f}, severity={result.severity}")
    
    # Test IQR method
    print("\n=== IQR anomaly detection ===")
    iqr_anomalies = detect_iqr_anomalies(normal_vals + [50.0, 60.0, -10.0])
    print(f"  Detected anomalies: {iqr_anomalies}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())