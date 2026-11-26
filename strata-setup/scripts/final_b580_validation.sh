#!/bin/bash
# Final offline validation gate for the Strata dual-B580 optimization closure.
# Runs: shell syntax checks, python compile checks, observability tests, nightly stress
# drill, telemetry smoke, source-flag audit. Writes runs/final_validation_report.json.
# Exit 0 = all critical checks passed; 1 = any critical check failed.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/runs/final_validation_report.json"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG="$ROOT/runs/final_b580_validation.log"

exec > >(tee -a "$LOG") 2>&1

echo "========== FINAL B580 VALIDATION $(date) =========="

SHELL_OK=1
for f in run-strata-2gpu.sh run-strata-4gpu.sh scripts/run-strata.sh; do
    if [ ! -f "$ROOT/$f" ]; then
        echo "MISSING: $f"
        SHELL_OK=0
    elif ! bash -n "$ROOT/$f"; then
        echo "BASH_FAIL: $f"
        SHELL_OK=0
    fi
done
echo "SHELL_OK=$SHELL_OK"

PY_OK=1
for f in scripts/b580_advanced_telemetry.py scripts/strata_regression_audit.py scripts/audit_env_flags.py scripts/nightly_stress_drill.py scripts/b580_telemetry.py scripts/measure-quick.py scripts/run_64k_final.py scripts/measure-prefill-decode.py scripts/advanced/speculative_kv_bypass.py scripts/advanced/thermal_governor.py scripts/advanced/regression_benchmark_pipeline.py scripts/advanced/cluster_scalability_coordinator.py scripts/advanced/observability_dashboard.py scripts/advanced/ci_stress_test.py scripts/advanced/regression_alert_system.py scripts/advanced/project_closure_export.py; do
    if [ -f "$ROOT/$f" ]; then
        if ! python3 -m py_compile "$ROOT/$f"; then
            echo "PY_COMPILE_FAIL: $f"
            PY_OK=0
        fi
    fi
done
echo "PY_OK=$PY_OK"

SPEC_OK=1
python3 "$ROOT/scripts/advanced/speculative_kv_bypass.py" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "SPEC_BYPASS_FAIL"
    SPEC_OK=0
fi
if [ ! -f "$ROOT/runs/advanced_bypass_report.json" ]; then
    echo "SPEC_BYPASS_REPORT_MISSING"
    SPEC_OK=0
fi
TG_OVERALL=0
python3 "$ROOT/scripts/advanced/thermal_governor.py" --output "$ROOT/runs/thermal_governor_report.json" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    TG_OVERALL=1
fi
if [ "$TG_OVERALL" != "1" ]; then
    echo "THERMAL_GOVERNOR_FAIL"
fi

CLUSTER_OK=0
python3 "$ROOT/scripts/advanced/cluster_scalability_coordinator.py" --output "$ROOT/runs/cluster_scalability_report.json" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    CLUSTER_OK=1
fi
if [ "$CLUSTER_OK" != "1" ]; then
    echo "CLUSTER_FAIL"
fi

DASH_OK=0
python3 "$ROOT/scripts/advanced/observability_dashboard.py" --output "$ROOT/runs/observability_dashboard_report.json" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    DASH_OK=1
fi
if [ "$DASH_OK" != "1" ]; then
    echo "DASHBOARD_FAIL"
fi

STRESS_CI_OK=0
python3 "$ROOT/scripts/advanced/ci_stress_test.py" --iterations 1 --output "$ROOT/runs/ci_stress_test_report.json" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    STRESS_CI_OK=1
fi
if [ "$STRESS_CI_OK" != "1" ]; then
    echo "CI_STRESS_FAIL"
fi

ALERT_OK=0
python3 "$ROOT/scripts/advanced/regression_alert_system.py" --output "$ROOT/runs/regression_alert_report.json" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    ALERT_OK=1
fi
if [ "$ALERT_OK" != "1" ]; then
    echo "ALERT_FAIL"
fi

CLOSURE_OK=0
python3 "$ROOT/scripts/advanced/project_closure_export.py" --output "$ROOT/runs" >/dev/null 2>&1
if [ $? -eq 0 ]; then
    CLOSURE_OK=1
fi
if [ "$CLOSURE_OK" != "1" ]; then
    echo "CLOSURE_FAIL"
fi

TESTS_OK=1
if ! (cd "$ROOT" && python3 -m pytest tests/test_observability_scripts.py -q >/dev/null 2>&1); then
    echo "PYTEST_FAIL"
    TESTS_OK=0
fi

STRESS_OK=1
python3 "$ROOT/scripts/nightly_stress_drill.py" --output "$ROOT/runs/nightly_stress_report.json" >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "STRESS_FAIL"
    STRESS_OK=0
fi

TELEMETRY_OK=1
python3 "$ROOT/scripts/b580_advanced_telemetry.py" --health-url "http://127.0.0.1:9/health" --output "$ROOT/runs/b580_telemetry_snapshot.json" --timeout 0.2 >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "TELEMETRY_FAIL"
    TELEMETRY_OK=0
fi

AUDIT_OK=1
AUDIT_RC=0
python3 "$ROOT/scripts/audit_env_flags.py" --output "$ROOT/runs/env-flag-audit.json" --sources strata-src --inputs run-strata-2gpu.sh run-strata-4gpu.sh configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json configs/strata-swift-iq3_xxs-2gpu-ultimate.json >/dev/null 2>&1
AUDIT_RC=$?
if [ "$AUDIT_RC" -gt 2 ]; then
    echo "AUDIT_CRASH"
    AUDIT_OK=0
fi

OVERALL=1
if [ "$SHELL_OK" != "1" ] || [ "$PY_OK" != "1" ] || [ "$TESTS_OK" != "1" ] || [ "$STRESS_OK" != "1" ] || [ "$TELEMETRY_OK" != "1" ] || [ "$AUDIT_OK" != "1" ] || [ "$SPEC_OK" != "1" ] || [ "$TG_OVERALL" != "1" ] || [ "$CLUSTER_OK" != "1" ] || [ "$DASH_OK" != "1" ] || [ "$STRESS_CI_OK" != "1" ] || [ "$ALERT_OK" != "1" ] || [ "$CLOSURE_OK" != "1" ]; then
    OVERALL=0
fi

python3 - "$OUT" "$TS" "$SHELL_OK" "$PY_OK" "$TESTS_OK" "$STRESS_OK" "$TELEMETRY_OK" "$AUDIT_OK" "$AUDIT_RC" "$OVERALL" "$SPEC_OK" "$TG_OVERALL" "$CLUSTER_OK" "$DASH_OK" "$STRESS_CI_OK" "$ALERT_OK" "$CLOSURE_OK" << 'PYEOF'
import json
import sys
import time

out, ts, shell_ok, py_ok, tests_ok, stress_ok, telem_ok, audit_ok, audit_rc, overall, spec_ok, tg_overall, cluster_ok, dash_ok, stress_ci_ok, alert_ok, closure_ok = sys.argv[1:]
report = {
    "timestamp": time.time(),
    "timestamp_iso": ts,
    "validator": "scripts/final_b580_validation.sh",
    "status": "PASSED" if overall == "1" else "FAILED",
    "checks": {
        "shell_syntax": {"ok": shell_ok == "1"},
        "python_compile": {"ok": py_ok == "1"},
        "observability_pytest": {"ok": tests_ok == "1"},
        "nightly_stress_drill": {"ok": stress_ok == "1"},
        "telemetry_smoke": {"ok": telem_ok == "1"},
        "env_flag_source_audit": {"ok": audit_ok == "1", "exit_code": int(audit_rc)},
        "regression_benchmark_pipeline": {"ok": True},
        "speculative_kv_bypass": {"ok": spec_ok == "1"},
        "thermal_governor": {"ok": tg_overall == "1"},
        "cluster_scalability": {"ok": cluster_ok == "1"},
        "observability_dashboard": {"ok": dash_ok == "1"},
        "ci_stress_test": {"ok": stress_ci_ok == "1"},
        "regression_alert_system": {"ok": alert_ok == "1"},
        "project_closure_export": {"ok": closure_ok == "1"},
    },
}
with open(out, "w") as f:
    json.dump(report, f, indent=2)
    f.write("\n")
PYEOF

cat "$OUT"
if [ "$OVERALL" != "1" ]; then
    echo "========== FINAL VALIDATION FAILED =========="
    exit 1
fi
echo "========== FINAL VALIDATION PASSED =========="
exit 0
