#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL_PATH="$HOME/data/models"
MODEL=""
IMAGE=vllm/vllm-openai-xpu:nightly
#IMAGE=intel/llm-scaler-vllm:0.21.0-b1
#IMAGE=urakozz/vllm-xpu-env:latest
CONFIG="$SCRIPT_DIR/config.yaml"
ENTRYPOINT="$SCRIPT_DIR/entrypoint.sh"

docker run --security-opt label=disable \
--pull always \
--rm -it \
--name=vllm \
-v "$MODEL_PATH":"$MODEL_PATH" \
--device /dev/dri:/dev/dri \
-v /dev/dri/by-path:/dev/dri/by-path \
-v "$CONFIG":/config.yaml \
-v "$ENTRYPOINT":/entrypoint.sh \
--shm-size=16gb \
--cap-add=SYS_ADMIN \
--cap-add=SYS_NICE \
--net=host \
--ulimit memlock=-1:-1 \
--privileged \
--entrypoint /entrypoint.sh \
-e http_proxy="" \
-e https_proxy="" \
$IMAGE \
--config /config.yaml
