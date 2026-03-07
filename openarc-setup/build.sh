#!/bin/bash

cd "$(dirname "$0")"

IMAGE_NAME="localhost/openarc"

echo "Capturing old image ID for $IMAGE_NAME..."
OLD_IMAGE_ID=$(docker images -q "$IMAGE_NAME")

echo "Building new image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" -f OpenArc/Dockerfile OpenArc/

NEW_IMAGE_ID=$(docker images -q "$IMAGE_NAME")

if [ -n "$OLD_IMAGE_ID" ] && [ "$OLD_IMAGE_ID" != "$NEW_IMAGE_ID" ]; then
    echo "Removing previous image $OLD_IMAGE_ID..."
    docker rmi "$OLD_IMAGE_ID" || true
else
    echo "No old image to remove or image ID hasn't changed."
fi

echo "Build complete."
