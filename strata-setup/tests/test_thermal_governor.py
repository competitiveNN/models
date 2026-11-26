"""Tests for the real Thermal & Power Envelope Governor engine."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "advanced"


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)


def test_thermal_governor_cli_help():
    r = run([sys.executable, str(SCRIPTS / "thermal_governor.py"), "--help"])
    assert r.returncode == 0
    assert "--output" in r.stdout
    assert "--interval" in r.stdout
    assert "--duration" in r.stdout
    assert "--device" in r.stdout


def test_thermal_governor_real_collection_writes_report(tmp_path):
    out = tmp_path / "gov.json"
    r = run([sys.executable, str(SCRIPTS / "thermal_governor.py"), "--output", str(out), "--interval", "1", "--duration", "2", "--device", "0", "--device", "1"])
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["status"] == "PASSED"
    assert data["governor_config"]["target_clock_mhz"] >= 2400
    sensors = data["telemetry"]["sensors"]
    assert set(sensors) == {"0", "1"}
    for dev in ("0", "1"):
        s = sensors[dev]
        assert "temperature_gpu_c" in s
        assert "power_draw_w" in s
        assert "clocks_current_graphics_mhz" in s
    assert data["telemetry"]["governance"]["valid_sensors_count"] == 2
    assert data["telemetry"]["governance"]["throttled"] is False


def test_thermal_governor_requires_sensors(tmp_path):
    out = tmp_path / "gov_fail.json"
    import importlib.util

    spec = importlib.util.spec_from_file_location("tg", SCRIPTS / "thermal_governor.py")
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)
    tg.collect_governor_telemetry = lambda ids: {"sensors": {}, "governance": {"throttled": False, "enforced": False, "valid_sensors_count": 0}}
    rc = tg.run_thermal_governor(output=str(out), device_ids=[0])
    assert rc != 0
    assert out.exists() and json.loads(out.read_text())["status"] == "SENSOR_UNAVAILABLE"
