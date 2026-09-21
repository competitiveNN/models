#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODELS_PATH="${MODELS_PATH:-$HOME/data/models}"
CONFIG_FILE="$SCRIPT_DIR/ovms_config.json"
API_KEY=abc
TAG=latest-gpu
#TAG=weekly
#TAG=local
mkdir -p "$SCRIPT_DIR/cache"

usage() {
    echo "Usage: $0 [build|run] [additional docker run args...]"
    echo ""
    echo "Commands:"
    echo "  build   Build the patched OVMS Docker image (openvino/model_server:local)"
    echo "  run     Run the OVMS container (default if no command specified)"
    echo ""
    echo "If no command is given, 'run' is assumed."
    echo ""
    echo "The build command invokes 'make docker_build' from the model_server/"
    echo "directory, which uses ov_use_binary=0 (builds OpenVINO + GenAI from"
    echo "source). The 4 GenAI patches in model_server/patches/ are applied"
    echo "during the build via the Dockerfile.ubuntu."
}

cmd_build() {
    cd "$SCRIPT_DIR/model_server" || exit 1
    echo "Building OVMS image (openvino/model_server:$TAG) from $PWD ..."
    echo "  ov_use_binary=0 (builds OpenVINO + GenAI from source)"
    echo "  ov_genai_branch=master"
    echo "  BASE_OS=ubuntu24"
    echo "  Patches: $(ls patches/ 2>/dev/null | wc -l) GenAI patches in model_server/patches/"
    echo ""
    echo "This may take 30-60 minutes depending on hardware (compiles OpenVINO + GenAI from source)."
    echo ""

    make docker_build \
        OV_USE_BINARY=0 \
        OV_GENAI_BRANCH=master \
        OV_GENAI_ORG=openvinotoolkit \
        OV_SOURCE_BRANCH=master \
        OV_SOURCE_ORG=openvinotoolkit \
        OV_TOKENIZERS_BRANCH=master \
        OV_TOKENIZERS_ORG=openvinotoolkit \
        BASE_OS=ubuntu24 \
        BASE_IMAGE=ubuntu:24.04 \
        OVMS_CPP_DOCKER_IMAGE=openvino/model_server \
        OVMS_CPP_IMAGE_TAG=local

    if [ $? -eq 0 ]; then
        echo ""
        echo "Build successful! Image tagged as openvino/model_server:$TAG"
        echo "Run with: $0 run"
    else
        echo ""
        echo "Build failed!"
        exit 1
    fi
}

cmd_run() {
    docker pull openvino/model_server:$TAG 2>/dev/null || true
    docker run \
      --security-opt label=disable \
      --privileged=true \
      --env API_KEY=$API_KEY \
      --net=host \
      --device /dev/dri \
      --device /dev/accel \
      --group-add=$(stat -c "%g" /dev/dri/render* | head -n 1) \
      --name ovms \
      --rm \
      -v $MODELS_PATH:/models:rw \
      -v $CONFIG_FILE:/config.json:ro \
      -v $SCRIPT_DIR/cache:/opt/cache:rw \
      openvino/model_server:$TAG \
      --log_level INFO \
      --config_path /config.json \
      --rest_port 8000 \
      "${@}"
}

case "${1:-run}" in
    build)
        cmd_build
        ;;
    run)
        shift
        cmd_run "$@"
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac
