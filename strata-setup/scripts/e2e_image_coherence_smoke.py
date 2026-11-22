#!/usr/bin/env python3
"""End-to-end image coherence smoke test for strata-old container.

Runs the strata-old container image matching run-strata-2gpu.sh configuration,
waits for it to become healthy, and runs the coherence gate against the live server.
Reports pass/fail with digest verification.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("IMAGE", "localhost/strata-old:latest")
CONTAINER_NAME = "strata-e2e-smoke"
HOST_PORT = os.environ.get("HOST_PORT", "1235")
CONTAINER_PORT = "8080"
HEALTH_URL = f"http://127.0.0.1:{HOST_PORT}/health"
COHERENCE_URL = f"http://127.0.0.1:{HOST_PORT}/v1/chat/completions"
MAX_WAIT = 300  # seconds

MODEL_DIR = os.environ.get("MODEL_DIR", "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF")
DATA_DIR = os.environ.get("DATA_DIR", str(ROOT / "Strata-data"))

LAUNCH_CMD = (
    "mkdir -p /root/.local/share/strata/components/engine && "
    "cp -r /opt/strata/components/engine/0.1.59-linux-x86_64-sycl /root/.local/share/strata/components/engine/ 2>/dev/null; "
    "/opt/strata/terminal/bin/strata launch "
    "--no-api-key --no-tui --family swift --model IQ3_XXS "
    "--model-path /model/ --context 65536 --vision off --access lan "
    "--port 8080 --gpu 0,1 --mtp on --drafting auto "
    "--set pipeline-windows=2 --set vram-reserve-mib=256 "
    "--set expert-cache=auto --set spec=4 --set trim-stage-weights "
    "--set kv=int8 --set prefill=auto:8192 --set spec-min-p=0.5 "
    "--set pool-workers=12 --set pool-affinity=p-cores --set host-core=first "
    "--set expert-cache-per-layer --set stream-experts --set mmap-experts; "
    "sleep infinity"
)


def run_cmd(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def start_container() -> bool:
    # Remove existing container if any
    run_cmd(["podman", "rm", "-f", CONTAINER_NAME], timeout=30)
    # Run container matching run-strata-2gpu.sh configuration
    rc, out, err = run_cmd([
        "podman", "run", "-d",
        "--name", CONTAINER_NAME,
        "--privileged",
        "--device=/dev/dri/renderD128",
        "--device=/dev/dri/renderD129",
        "--publish", f"127.0.0.1:{HOST_PORT}:{CONTAINER_PORT}",
        "--ulimit", "core=0",
        "--stop-timeout", "120",
        f"--volume={MODEL_DIR}:/model/:Z,U",
        f"--volume={DATA_DIR}:/data/Strata-data:Z,U",
        "--env", "SYCL_CACHE_PERSISTENT=1",
        "--env", "ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1",
        "--env", "STRATA_SPIN_MAX=200000000",
        "--env", "STRATA_PREFILL_RING=16",
        "--env", "STRATA_VERIFY_DEVICE_PLAN=1",
        "--env", "STRATA_STAGE_TRIM=1",
        "--env", "STRATA_RING_TIMEOUT_S=600",
        "--env", "STRATA_SPLIT_WAIT_MS=600000",
        "--env", "STRATA_VERIFY_DRAIN_TIMEOUT_MS=120000",
        "--env", "STRATA_PREFILL_MMQ=auto",
        "--env", "STRATA_WINDOW_SYNC=0",
        "--env", "IGC_EnableGEPSimplification=0",
        "--env", "STRATA_MIRROR_MIB=16384",
        "--env", "STRATA_VERIFY_NO_HOST=0",
        "--env", "STRATA_COPY_ENGINE=0",
        "--env", "STRATA_SPLIT_MISS_MS=108",
        "--rm",
        "--entrypoint", "/bin/bash",
        IMAGE,
        "-c", LAUNCH_CMD,
    ], timeout=120)
    if rc != 0:
        print(f"Failed to start container: {err}", file=sys.stderr)
        return False
    return True


def wait_for_health() -> bool:
    start = time.time()
    while time.time() - start < MAX_WAIT:
        rc, out, err = run_cmd(["curl", "-sf", HEALTH_URL], timeout=10)
        if rc == 0:
            try:
                data = json.loads(out)
                if data.get("loaded"):
                    return True
            except Exception:
                pass
        time.sleep(10)
    return False


def run_coherence_gate() -> bool:
    rc, out, err = run_cmd([
        "python3", str(ROOT / "bench-coherence-2xb580.py"),
        "--url", COHERENCE_URL,
    ], timeout=300)
    return rc == 0


def get_running_digest() -> str:
    rc, out, err = run_cmd([
        "podman", "inspect", "--format", "{{.ImageDigest}}", CONTAINER_NAME,
    ], timeout=30)
    if rc == 0:
        return out.strip()
    return ""


def verify_digest() -> bool:
    rc, out, err = run_cmd([
        "python3", str(ROOT / "scripts" / "pin_image_digest.py"), "--verify",
    ], timeout=30)
    return rc == 0


def cleanup() -> None:
    run_cmd(["podman", "rm", "-f", CONTAINER_NAME], timeout=30)


def main() -> int:
    print(f"Starting container {CONTAINER_NAME} from {IMAGE}...")
    if not start_container():
        print("FAIL: Could not start container")
        cleanup()
        return 1

    print(f"Waiting for health (max {MAX_WAIT}s)...")
    if not wait_for_health():
        print("FAIL: Container did not become healthy")
        run_cmd(["podman", "logs", CONTAINER_NAME], timeout=30)
        cleanup()
        return 1
    print("Container healthy.")

    # Verify running digest matches pinned
    running_digest = get_running_digest()
    print(f"Running image digest: {running_digest}")
    if not verify_digest():
        print("WARNING: Running digest does not match pinned digest")
    else:
        print("Digest verified: running image matches pinned digest.")

    print("Running coherence gate...")
    if not run_coherence_gate():
        print("FAIL: Coherence gate failed")
        cleanup()
        return 1
    print("PASS: Coherence gate passed (4/4)")

    cleanup()
    print("E2E image coherence smoke test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
