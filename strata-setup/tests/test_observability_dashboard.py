"""Tests for the Advanced Telemetry Monitoring Dashboard."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_observability_dashboard_cli_help():
    r = run([sys.executable, str(SCRIPTS / "observability_dashboard.py"), "--help"])
    assert r.returncode == 0
    assert "--output" in r.stdout


def test_observability_dashboard_writes_report(tmp_path):
    out = tmp_path / "dashboard.json"
    r = run([sys.executable, str(SCRIPTS / "observability_dashboard.py"), "--output", str(out)])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "HEALTHY"
    assert "metrics_summary" in data
    assert data["metrics_summary"]["decode_tok_s"] >= 50.0
    assert data["metrics_summary"]["prefill_64k_tok_s"] >= 2000.0
    assert out.exists()
