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
	DOCKERFILE=".devops/openvino.Dockerfile"
	CONTEXT="llama.cpp"
	EXTRA_ARGS=""
	;;
intel)
	IMAGE_TAG="llama-cpp-intel"
	DOCKERFILE=".devops/intel.Dockerfile"
	CONTEXT="llama.cpp"
	EXTRA_ARGS="--build-arg=GGML_SYCL_F16=ON"
	;;
vulkan)
	IMAGE_TAG="llama-cpp-vulkan"
	DOCKERFILE=".devops/vulkan.Dockerfile"
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

build_image() {
	local IMAGE_TAG=$1
	local DOCKERFILE=$2
	local CONTEXT=$3
	local EXTRA_ARGS=$4

	# Special handling for ik_llama_cpu: patch Dockerfile to include llama-bench binary in server stage
	local USE_TEMP_DOCKERFILE=0
	local TEMP_DOCKERFILE=""
	if [ "$IMAGE_TAG" = "ik-llama-cpu" ]; then
		if [ -f "$DOCKERFILE" ]; then
			TEMP_DOCKERFILE=$(mktemp)
			cp "$DOCKERFILE" "$TEMP_DOCKERFILE"
			# Insert COPY for llama-bench in server stage, right after the llama-server COPY line
			sed -i '/COPY --from=build \/app\/dist\/bin\/llama-server \/app\/llama-server/a COPY --from=build /app/dist/bin/llama-bench /app/llama-bench' "$TEMP_DOCKERFILE"
			DOCKERFILE="$TEMP_DOCKERFILE"
			USE_TEMP_DOCKERFILE=1
		else
			echo "Warning: Dockerfile $DOCKERFILE not found, cannot patch for ik_llama_cpu" >&2
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

	# Cleanup temporary Dockerfile if used
	if [ "$USE_TEMP_DOCKERFILE" -eq 1 ] && [ -f "$TEMP_DOCKERFILE" ]; then
		rm -f "$TEMP_DOCKERFILE"
	fi
}

build_image "$IMAGE_TAG" "$DOCKERFILE" "$CONTEXT" "$EXTRA_ARGS"
