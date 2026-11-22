#!/usr/bin/env python3
"""End-to-end image coherence smoke test for strata-old container.

Runs the strata-old container image, waits for it to become healthy,
and runs the coherence gate against the live server. Reports pass/fail.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "localhost/strata-old:latest"
CONTAINER_NAME = "strata-e2e-smoke"
HEALTH_URL = "http://127.0.0.1:1235/health"
COHERENCE_URL = "http://127.0.0.1:1235/v1/chat/completions"
MAX_WAIT = 300  # seconds


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
    # Run container with host networking
    rc, out, err = run_cmd([
        "podman", "run", "-d", "--name", CONTAINER_NAME,
        "--network", "host", "--privileged",
        "--device", "/dev/dri",
        IMAGE,
    ], timeout=60)
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