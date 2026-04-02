#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_PATH="$HOME/data/models"
MODEL=""
IMAGE=intel/vllm
#IMAGE=localhost/vllm-xpu-env:latest
#IMAGE=intel/llm-scaler-vllm
CONFIG="$SCRIPT_DIR/vllm.yaml"
ENTRYPOINT="$SCRIPT_DIR/entrypoint.sh"

docker run --security-opt label=disable \
--rm -it \
--name=vllm \
--net=host \
-v "$MODEL_PATH":"$MODEL_PATH" \
--device /dev/dri:/dev/dri \
-v /dev/dri/by-path:/dev/dri/by-path \
-v "$CONFIG":/config.yaml \
-v "$ENTRYPOINT":/vllm.sh \
--ipc=host \
--privileged \
--entrypoint /bin/bash \
$IMAGE \
-lic "vllm serve --config /config.yaml"

