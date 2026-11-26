"""Tests for the Multi-Node Cluster Scalability Coordinator."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_cluster_scalability_cli_help():
    r = run([sys.executable, str(SCRIPTS / "cluster_scalability_coordinator.py"), "--help"])
    assert r.returncode == 0
    assert "--output" in r.stdout


def test_cluster_scalability_writes_report(tmp_path):
    out = tmp_path / "cluster.json"
    r = run([sys.executable, str(SCRIPTS / "cluster_scalability_coordinator.py"), "--output", str(out)])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "HEALTHY"
    assert data["cluster_summary"]["healthy_nodes"] > 0
    assert data["cluster_summary"]["total_gpus"] >= 4
    assert data["cluster_summary"]["aggregate_forecast_decode_tok_s"] > 0
    assert out.exists()
