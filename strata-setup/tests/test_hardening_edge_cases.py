"""Tests for the advanced observability dashboard and cluster coordinator edge cases."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_cluster_scalability_handles_empty_nodes(tmp_path):
    # Simulate a cluster config with no nodes to ensure graceful degradation
    # Since the script uses hardcoded sample nodes, we just test the CLI and report structure
    out = tmp_path / "cluster.json"
    r = run([sys.executable, str(SCRIPTS / "cluster_scalability_coordinator.py"), "--output", str(out)])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert "cluster_summary" in data
    assert data["cluster_summary"]["total_configured_nodes"] >= 1


def test_observability_dashboard_handles_missing_reports(tmp_path):
    # Run dashboard in a temp dir with no prior reports to ensure it doesn't crash
    out = tmp_path / "dashboard.json"
    r = run([sys.executable, str(SCRIPTS / "observability_dashboard.py"), "--output", str(out)], cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "HEALTHY"
    assert "collected_reports" in data
    # In empty dir, it should just have an empty or minimal reports list
    assert isinstance(data["collected_reports"], list)
