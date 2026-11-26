import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_speculative_kv_bypass_cli_help():
    r = run([sys.executable, str(SCRIPTS / "speculative_kv_bypass.py"), "--help"])
    assert r.returncode == 0
    assert "--output" in r.stdout
    assert "--draft-tokens" in r.stdout
    assert "--spec-min-p" in r.stdout
    assert "--kv-mode" in r.stdout


def test_speculative_kv_bypass_writes_success_report(tmp_path):
    out = tmp_path / "bypass.json"
    r = run([sys.executable, str(SCRIPTS / "speculative_kv_bypass.py"), "--output", str(out)])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "SUCCESS"
    cfg = data["configuration"]
    assert cfg["speculative_decoding"]["enabled"] is True
    assert cfg["kv_quantization"]["mode"] == "int4_mixed"
    assert cfg["dma_overlap"]["async_ring_buffer"] is True
    assert data["measured_boosted_performance"]["decode_tok_s"] > 0
    assert data["measured_boosted_performance"]["prefill_64k_tok_s"] > 0
