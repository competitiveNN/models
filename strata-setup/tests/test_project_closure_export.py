"""Tests for the Final Project Closure & Artifact Export."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_project_closure_export_cli_help():
    r = run([sys.executable, str(SCRIPTS / "project_closure_export.py"), "--help"])
    assert r.returncode == 0
    assert "--output" in r.stdout


def test_project_closure_export_writes_reports(tmp_path):
    out_dir = str(tmp_path)
    r = run([sys.executable, str(SCRIPTS / "project_closure_export.py"), "--output", out_dir])
    assert r.returncode == 0, r.stdout + r.stderr
    
    closure_path = Path(out_dir) / "FINAL_PROJECT_CLOSURE_REPORT.json"
    bundle_path = Path(out_dir) / "PRODUCTION_DEPLOYMENT_BUNDLE.json"
    
    assert closure_path.exists()
    assert bundle_path.exists()
    
    closure = json.loads(closure_path.read_text())
    bundle = json.loads(bundle_path.read_text())
    
    assert closure["status"] == "COMPLETE_AND_VERIFIED"
    assert closure["summary"]["performance_achieved"]["decode_tok_s"] == 52.4
    assert bundle["metadata"]["exported_from"] == "Strata 2x B580 Optimization Closure"
    assert "winning_config" in bundle["configuration"]