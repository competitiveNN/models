"""Tests for the Automated Multi-Node Benchmark Regression Alert System."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_regression_alert_cli_help():
    r = run([sys.executable, str(SCRIPTS / "regression_alert_system.py"), "--help"])
    assert r.returncode == 0
    assert "--output" in r.stdout


def test_regression_alert_writes_report(tmp_path):
    out = tmp_path / "alerts.json"
    # Should pass/warn if dashboard missing, but return 0 or handle gracefully based on impl
    # Our impl returns 0 if PASSED (even with warning, status is PASSED in logic? Let's check)
    # Wait, logic: if missing, appends WARNING but status remains PASSED.
    r = run([sys.executable, str(SCRIPTS / "regression_alert_system.py"), "--output", str(out)], cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert "status" in data
    assert "alerts" in data
    assert out.exists()
