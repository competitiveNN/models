#!/bin/bash


MODEL_PATH="$HOME/data/models"
MODEL=""
IMAGE=intel/vllm
#IMAGE=localhost/vllm-xpu-env:latest
CONFIG="$PWD/vllm.yaml"

docker run --security-opt label=disable \
--rm -it \
--net=host \
-v "$MODEL_PATH":"$MODEL_PATH" \
--device /dev/dri:/dev/dri \
-v /dev/dri/by-path:/dev/dri/by-path \
-v "$CONFIG":/config.yaml \
--ipc=host \
--privileged \
$IMAGE \
--config /config.yaml \
$@
