#!/bin/sh
# Run the Strata server for Swift 1.5 IQ2_XS on Intel Arc B580 (SYCL port).
# Everything runs inside the strata-sycl-dev container (the engine needs the
# oneAPI runtime and the GPU device). The host's strata-setup folder is mounted
# at /work inside it.
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
docker run --rm --privileged --device /dev/dri \
    --name strata-server \
    --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/strata-swift-iq2_xs.json --port 8081"