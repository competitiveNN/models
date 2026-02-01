#!/bin/bash


MODEL_PATH="$HOME/data/models"
DEVICES="--device /dev/dri/card0:/dev/dri/card0 --device /dev/dri/renderD128:/dev/dri/renderD128 --device /dev/dri/card1:/dev/dri/card1 --device /dev/dri/renderD129:/dev/dri/renderD129"
MODEL=""
IMAGE=intel/vllm
CONFIG="$PWD/vllm.yaml"

docker run --security-opt label=disable \
--rm -it \
--env OPENARC_API_KEY=abc \
--net=host \
-v "$MODEL_PATH":"$MODEL_PATH" \
$DEVICES \
-v /dev/dri/by-path:/dev/dri/by-path \
-v "$CONFIG":/config \
--ipc=host \
$IMAGE \
--config /config\
$@
