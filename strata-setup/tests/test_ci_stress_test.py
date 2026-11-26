"""Tests for the CI Stress-Testing Routine."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_ci_stress_test_cli_help():
    r = run([sys.executable, str(SCRIPTS / "ci_stress_test.py"), "--help"])
    assert r.returncode == 0
    assert "--iterations" in r.stdout
    assert "--output" in r.stdout


def test_ci_stress_test_writes_report(tmp_path):
    out = tmp_path / "stress.json"
    r = run([sys.executable, str(SCRIPTS / "ci_stress_test.py"), "--iterations", "1", "--output", str(out)])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "PASSED"
    assert data["iterations"] == 1
    assert len(data["results"]) == 1
    assert out.exists()
