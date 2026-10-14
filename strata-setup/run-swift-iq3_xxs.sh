#!/bin/sh
# Run the Strata server for Swift 1.5 IQ3_XXS on 2x Intel Arc B580 (SYCL port).
# Everything runs inside the strata-sycl-dev container (the engine needs the
# oneAPI runtime and the GPU device). The host's strata-setup folder is mounted
# at /work inside it.
#
# Usage: ./run-swift-iq3_xxs.sh [gpu.0 | gpu.0,gpu.1 | 0 | 0,1]
#   gpu.0        one GPU (default). Fastest for this model: 38-43 tok/s decode
#                (the layer split pays a PCIe hand-off every verify window).
#   gpu.0,gpu.1  both GPUs as a layer split: each card holds its own 18 layers'
#                expert cache (~3900+2800 slots). Measured 25-31 tok/s warm on
#                engine 0.1.44.1 (2-GPU pays a PCIe hand-off per verify window,
#                so single card stays faster for this model).
#   0 / 0,1      bare numbers work too. Any card list the server accepts.
#
# Uses podman directly: the host's `docker` is a shim that runs podman via
# flatpak-spawn, which only resolves on the host, not inside a toolbox.
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"

SPEC="${1:-gpu.0}"
# "gpu.0,gpu.1" -> "0,1" (the server's --gpu takes nvidia-smi-style numbers)
GPUS="$(printf '%s\n' "$SPEC" | sed 's/gpu\.//g')"
if ! printf '%s\n' "$GPUS" | grep -Eq '^[0-9]+(,[0-9]+)*$'; then
    echo "run-swift-iq3_xxs.sh: bad GPU spec '$SPEC' (want gpu.0 or gpu.0,gpu.1)" >&2
    exit 2
fi

exec podman run --rm --privileged --device /dev/dri \
    --name strata-server --replace \
    --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/strata-swift-iq3_xxs.json --gpu '$GPUS' --port 8081"
