#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_PATH="$HOME/data/models"
MODEL=""
IMAGE=intel/vllm
#IMAGE=localhost/vllm-xpu-env:latest
#IMAGE=intel/llm-scaler-vllm
CONFIG="$SCRIPT_DIR/vllm.yaml"

docker run --security-opt label=disable \
--rm -it \
--name=vllm \
--net=host \
-v "$MODEL_PATH":"$MODEL_PATH" \
--device /dev/dri:/dev/dri \
-v /dev/dri/by-path:/dev/dri/by-path \
-v "$CONFIG":/config.yaml \
--ipc=host \
--privileged \
--entrypoint bash \
$IMAGE \
-lic "vllm serve --config /config.yaml"
