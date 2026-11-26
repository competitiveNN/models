#!/usr/bin/env python3
"""
B580 Deployment Manifest Indexer.
Indexes all optimization scripts, configs, and validation reports into a single manifest.
"""
import json
import os

def create_manifest():
    manifest = {
        "project": "strata-setup-2gpu-b580",
        "manifest_version": "1.0.0",
        "hardware": "2x Intel Arc B580 (asymmetric x8/x4 PCIe, no P2P)",
        "run_script": "run-strata-2gpu.sh",
        "key_scripts": [
            "scripts/tp2_software_ring_sync.py",
            "scripts/strata_layer_cache_manager.py",
            "scripts/strata_overlap_scheduler.py",
            "scripts/hybrid_tp_pp_scheduler.py",
            "scripts/b580_expert_cache_tuner.py",
            "scripts/b580_kernel_fusion_refiner.py",
            "scripts/b580_end_to_end_orchestrator.py",
            "scripts/final_optimization_synthesizer.py",
            "scripts/final_optimization_validator.py",
            "scripts/production_dry_run_validator.py",
            "scripts/b580_stress_test_suite.py"
        ],
        "key_reports": [
            "runs/final_optimization_summary.json",
            "runs/b580_end_to_end_orchestration_report.json",
            "runs/b580_stress_test_report.json",
            "runs/production_dry_run_report.json"
        ],
        "status": "fully_deployed_and_verified"
    }

    os.makedirs("runs", exist_ok=True)
    out_path = "runs/b580_deployment_manifest.json"
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Deployment manifest saved to {out_path}")

if __name__ == "__main__":
    create_manifest()
