#!/bin/bash

MODELS_PATH="${MODELS_PATH:-$HOME/data/models}"
CONFIG_FILE="$(pwd)/ovms_config.json"
API_KEY=abc
#TAG=latest-gpu
TAG=latest-py

docker run \
  --security-opt label=disable \
  --user $(id -u):$(id -g) \
  --env API_KEY=$API_KEY \
  --net=host \
  --device /dev/dri \
  --device /dev/accel \
  --group-add=$(stat -c "%g" /dev/dri/render* | head -n 1) \
  --name ovms \
  --rm \
  -v $MODELS_PATH:/models:rw \
  -v $CONFIG_FILE:/config.json:ro \
  openvino/model_server:$TAG \
  --config_path /config.json \
  --rest_port 8000
  
