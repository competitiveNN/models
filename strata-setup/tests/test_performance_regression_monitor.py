"""Tests for the Continuous Automated Performance Regression Monitor."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_performance_regression_monitor_cli_help():
    r = run([sys.executable, str(SCRIPTS / "performance_regression_monitor.py"), "--help"])
    assert r.returncode == 0
    assert "--update-baseline" in r.stdout
    assert "--decode-threshold" in r.stdout
    assert "--prefill-threshold" in r.stdout
    assert "--output" in r.stdout


def test_performance_regression_monitor_writes_report(tmp_path):
    out = tmp_path / "regression_monitor.json"
    r = run([sys.executable, str(SCRIPTS / "performance_regression_monitor.py"), "--output", str(out)])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert "status" in data
    assert "current_metrics" in data or "reason" in data
    assert out.exists()


def test_performance_regression_monitor_update_baseline(tmp_path):
    # Test updating baseline
    out = tmp_path / "regression_monitor2.json"
    baseline_file = tmp_path / "performance_baseline.json"
    # Temporarily redirect baseline file
    import os
    old_baseline = os.environ.get("PERF_BASELINE_FILE")
    os.environ["PERF_BASELINE_FILE"] = str(baseline_file)
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "performance_regression_monitor.py"), "--update-baseline", "--output", str(out)], cwd=ROOT, text=True, capture_output=True, check=False, env=os.environ)
        assert r.returncode == 0, r.stdout + r.stderr
        assert baseline_file.exists()
    finally:
        if old_baseline:
            os.environ["PERF_BASELINE_FILE"] = old_baseline
        else:
            del os.environ["PERF_BASELINE_FILE"]