#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

MODEL_PATH="$HOME/data/models"
DEVICES="--device /dev/accel:/dev/accel --device /dev/dri/card0:/dev/dri/card0 --device /dev/dri/renderD128:/dev/dri/renderD128 --device /dev/dri/card1:/dev/dri/card1 --device /dev/dri/renderD129:/dev/dri/renderD129"
MODEL=""
IMAGE=localhost/openarc

run_container() {
    docker run --security-opt label=disable \
    --rm -it \
    --name openarc \
    --env OPENARC_API_KEY=abc \
    --net=host \
    -v "$MODEL_PATH":"$MODEL_PATH" \
    -v "$SCRIPT_DIR/openarc-entrypoint.sh:/openarc-entrypoint.sh" \
    --entrypoint=/openarc-entrypoint.sh \
    $DEVICES \
    $IMAGE \
    "$@"
}

if [ "$1" = "--detect-devices" ]; then
    run_container tool device-detect
    exit $?
fi

run_container serve start
# $MODEL
