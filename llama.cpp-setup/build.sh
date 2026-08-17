#!/bin/bash
set -e

BACKEND=$1

# Pass --build-arg=GGML_SYCL_DEVICE_ARCH=bmg_g21 to SYCL builds when WITH_SYCL_ARCH=1.
# Default is off (the Dockerfile/SYCL runtime selects the GPU arch).
WITH_SYCL_ARCH="${WITH_SYCL_ARCH:-0}"

if [ "$WITH_SYCL_ARCH" = "1" ]; then
	SYCL_DEVICE_ARCH_ARG="--build-arg=GGML_SYCL_DEVICE_ARCH=bmg_g21"
else
	SYCL_DEVICE_ARCH_ARG=""
fi

if [ -z "$BACKEND" ]; then
	echo "Usage: $0 <backend>"
	echo "Supported backends: openvino, intel, vulkan, ik_llama_cpu, bee_intel, bee_vulkan"
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
	EXTRA_ARGS="--build-arg=GGML_SYCL_F16=ON --build-arg=GGML_SYCL_DNN=ON --build-arg=GGML_SYCL_GRAPH=ON --build-arg=GGML_SYCL_HOST_MEM_FALLBACK=ON --build-arg=GGML_SYCL_SUPPORT_LEVEL_ZERO_API=ON $SYCL_DEVICE_ARCH_ARG"
	;;
vulkan)
	IMAGE_TAG="llama-cpp-vulkan"
	DOCKERFILE="llama.cpp/.devops/vulkan.Dockerfile"
	CONTEXT="llama.cpp"
	EXTRA_ARGS=""
	;;
bee_intel)
	IMAGE_TAG="bee-llama-cpp-intel"
	DOCKERFILE="beellama.cpp/.devops/intel.Dockerfile"
	CONTEXT="beellama.cpp"
	EXTRA_ARGS="--build-arg=GGML_SYCL_F16=ON $SYCL_DEVICE_ARCH_ARG"
	;;
bee_vulkan)
	IMAGE_TAG="bee-llama-cpp-vulkan"
	DOCKERFILE="beellama.cpp/.devops/vulkan.Dockerfile"
	CONTEXT="beellama.cpp"
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
	echo "Supported backends: openvino, intel, vulkan, ik_llama_cpu, bee_intel, bee_vulkan"
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
