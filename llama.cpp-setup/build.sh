#!/bin/bash
set -e

BACKEND=$1

if [ -z "$BACKEND" ]; then
	echo "Usage: $0 <backend>"
	echo "Supported backends: openvino, intel, vulkan, ik_llama_cpu"
	exit 1
fi

case $BACKEND in
openvino)
	IMAGE_TAG="llama-cpp-openvino"
	DOCKERFILE="llama.cpp/.devops/openvino.Dockerfile"
	CONTEXT="llama.cpp"
	EXTRA_ARGS=""
	;;
intel)
	IMAGE_TAG="llama-cpp-intel"
	DOCKERFILE="llama.cpp/.devops/intel.Dockerfile"
	CONTEXT="llama.cpp"
	EXTRA_ARGS="--build-arg=GGML_SYCL_F16=ON"
	;;
vulkan)
	IMAGE_TAG="llama-cpp-vulkan"
	DOCKERFILE="llama.cpp/.devops/vulkan.Dockerfile"
	CONTEXT="llama.cpp"
	EXTRA_ARGS=""
	;;
ik_llama_cpu)
	IMAGE_TAG="ik-llama-cpu"
	DOCKERFILE="ik_llama.cpp/docker/ik_llama-cpu.Containerfile"
	CONTEXT="ik_llama.cpp"
	EXTRA_ARGS=""
	;;
*)
	echo "Unknown backend: $BACKEND"
	echo "Supported backends: openvino, intel, vulkan, ik_llama_cpu"
	exit 1
	;;
esac

patch_for_native() {
	local DOCKERFILE="$1"

	if [ ! -f "$DOCKERFILE" ]; then
		echo "Warning: Dockerfile $DOCKERFILE not found, cannot patch for GGML_NATIVE=ON" >&2
		echo ""
		return 1
	fi

	TEMP_DOCKERFILE=$(mktemp "${TMPDIR:-/tmp}/Dockerfile.native.patch.XXXXXX")
	cp "$DOCKERFILE" "$TEMP_DOCKERFILE"

	if grep -q 'GGML_NATIVE=OFF' "$TEMP_DOCKERFILE"; then
		sed -i 's/GGML_NATIVE=OFF/GGML_NATIVE=ON/g' "$TEMP_DOCKERFILE"
	elif grep -q 'GGML_NATIVE=ON' "$TEMP_DOCKERFILE"; then
		:
	else
		python3 << 'ENDPATCH'
import re
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

new_content = re.sub(
    r'(cmake -B build/ReleaseOV -G Ninja \\\n        -DCMAKE_BUILD_TYPE=Release \\\n        -DGGML_OPENVINO=ON)(&&)',
    r'\1\n        -DGGML_NATIVE=ON\2',
    content
)

with open(sys.argv[1], 'w') as f:
    f.write(new_content)
ENDPATCH
	fi

	echo "$TEMP_DOCKERFILE"
}

build_image() {
	local IMAGE_TAG=$1
	local DOCKERFILE=$2
	local CONTEXT=$3
	local EXTRA_ARGS=$4

	local USE_TEMP_DOCKERFILE=0
	local TEMP_DOCKERFILE=""
	if [ "$IMAGE_TAG" = "ik-llama-cpu" ]; then
		if [ -f "$DOCKERFILE" ]; then
			TEMP_DOCKERFILE=$(mktemp)
			cp "$DOCKERFILE" "$TEMP_DOCKERFILE"
			sed -i '/COPY --from=build \/app\/dist\/bin\/llama-server \/app\/llama-server/a COPY --from=build /app/dist/bin/llama-bench /app/llama-bench' "$TEMP_DOCKERFILE"
			DOCKERFILE="$TEMP_DOCKERFILE"
			USE_TEMP_DOCKERFILE=1
		else
			echo "Warning: Dockerfile $DOCKERFILE not found, cannot patch for ik_llama_cpu" >&2
		fi
	else
		TEMP_DOCKERFILE=$(patch_for_native "$DOCKERFILE")
		if [ -n "$TEMP_DOCKERFILE" ] && [ -f "$TEMP_DOCKERFILE" ]; then
			DOCKERFILE="$TEMP_DOCKERFILE"
			USE_TEMP_DOCKERFILE=1
		fi
	fi

	local OLD_IMAGE_ID=$(docker images -q "$IMAGE_TAG")

	if [ -n "$EXTRA_ARGS" ]; then
		docker build -t "$IMAGE_TAG" $EXTRA_ARGS --target server -f "$DOCKERFILE" "$CONTEXT"
	else
		docker build -t "$IMAGE_TAG" --target server -f "$DOCKERFILE" "$CONTEXT"
	fi

	local NEW_IMAGE_ID=$(docker images -q "$IMAGE_TAG")

	if [ -n "$OLD_IMAGE_ID" ] && [ "$OLD_IMAGE_ID" != "$NEW_IMAGE_ID" ]; then
		echo "Removing previous image $OLD_IMAGE_ID..."
		docker rmi "$OLD_IMAGE_ID" || true
	fi

	if [ "$USE_TEMP_DOCKERFILE" -eq 1 ] && [ -f "$TEMP_DOCKERFILE" ]; then
		rm -f "$TEMP_DOCKERFILE"
	fi
}

build_image "$IMAGE_TAG" "$DOCKERFILE" "$CONTEXT" "$EXTRA_ARGS"
