#!/bin/bash
set -e

build_image() {
    local IMAGE_TAG=$1
    local DOCKERFILE=$2
    local EXTRA_ARGS=$3

    local OLD_IMAGE_ID=$(docker images -q "$IMAGE_TAG")

    if [ -n "$EXTRA_ARGS" ]; then
        docker build -t "$IMAGE_TAG" $EXTRA_ARGS --target server -f "$DOCKERFILE" llama.cpp
    else
        docker build -t "$IMAGE_TAG" --target server -f "$DOCKERFILE" llama.cpp
    fi

    local NEW_IMAGE_ID=$(docker images -q "$IMAGE_TAG")

    if [ -n "$OLD_IMAGE_ID" ] && [ "$OLD_IMAGE_ID" != "$NEW_IMAGE_ID" ]; then
        echo "Removing previous image $OLD_IMAGE_ID..."
        docker rmi "$OLD_IMAGE_ID" || true
    fi
}

#build_image "llama-cpp-openvino" ".devops/openvino.Dockerfile" ""
build_image "llama-cpp-intel" ".devops/intel.Dockerfile" "--build-arg=GGML_SYCL_F16=ON"
#build_image "llama-cpp-vulkan" ".devops/vulkan.Dockerfile" ""
