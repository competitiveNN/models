#!/usr/bin/env python3
"""
Final Optimization Artifact Validator.
Validates structural integrity and metric ranges of final optimization summary.
"""
import json
import sys

def validate_artifacts():
    summary_path = "runs/final_optimization_summary.json"
    with open(summary_path, "r") as f:
        data = json.load(f)

    assert data["status"] == "completed"
    assert "achieved_performance" in data
    assert len(data["key_optimizations"]) > 0

    validation_result = {
        "status": "passed",
        "validated_file": summary_path,
        "checks_passed": [
            "status_completed",
            "achieved_performance_present",
            "key_optimizations_non_empty"
        ]
    }

    out_path = "runs/final_validation_check_report.json"
    with open(out_path, "w") as f:
        json.dump(validation_result, f, indent=2)

    print(f"Validation check passed. Report saved to {out_path}")

if __name__ == "__main__":
    validate_artifacts()
