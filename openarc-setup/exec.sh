#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

if [ -z "$1" ]; then
    echo "Usage: exec.sh <openarc-command>"
    exit 1
fi

# Check if container is running
if ! docker ps --filter "name=openarc" --format "{{.Names}}" | grep -q "openarc"; then
    echo "Error: openarc container is not running"
    echo "Start it first with: $SCRIPT_DIR/openarc.sh"
    exit 1
fi

# Forward arguments to openarc in the container
exec_args=("openarc" "$@")
docker exec -it openarc "${exec_args[@]}"
