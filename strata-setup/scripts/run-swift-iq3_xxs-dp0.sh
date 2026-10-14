#!/bin/sh
# 2-GPU run with STRATA_VERIFY_DEVICE_PLAN=0 (device-plan path off, doorbell graph + deadlock fix).
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec docker run --rm --privileged --device /dev/dri \
    --name strata-server --replace \
    --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/strata-swift-iq3_xxs-dp0.json --port 8081"