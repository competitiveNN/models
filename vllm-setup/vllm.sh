#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_PATH="$HOME/data/models"
MODEL=""
IMAGE=intel/vllm
#IMAGE=localhost/vllm-xpu-env:latest
CONFIG="$SCRIPT_DIR/vllm.yaml"

docker run --security-opt label=disable \
--rm -it \
--name=vllm \
--net=host \
--env VLLM_DISABLE_COMPILE_CACHE=1 \
--env TORCH_COMPILE_DISABLE=1 \
--env VLLM_TORCH_COMPILE_LEVEL=0 \
-v "$MODEL_PATH":"$MODEL_PATH" \
--device /dev/dri:/dev/dri \
-v /dev/dri/by-path:/dev/dri/by-path \
-v "$CONFIG":/config.yaml \
--ipc=host \
--privileged \
$IMAGE \
--config /config.yaml \
$@
