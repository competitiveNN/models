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

# Apply a temporary GGML_NATIVE=ON patch to a Dockerfile.
# Handles three cases:
#   1. Has ...GGML_NATIVE=OFF...  → replace with =ON
#   2. Has ...GGML_NATIVE=ON...   → already correct, no change
#   3. Has no GGML_NATIVE at all  → append -DGGML_NATIVE=ON after the cmake invocation
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
		# Case 1: GGML_NATIVE exists and is OFF → flip to ON
		sed -i 's/GGML_NATIVE=OFF/GGML_NATIVE=ON/g' "$TEMP_DOCKERFILE"
	elif grep -q 'GGML_NATIVE=ON' "$TEMP_DOCKERFILE"; then
		# Case 2: Already ON — leave as-is
		:
	else
		# Case 3: GGML_NATIVE absent → append -DGGML_NATIVE=ON after the cmake invocation line
		sed -i '/cmake.*-S\|cmake.*-B.*Release\|cmake.*-B.*build/a\\t\t-DGGML_NATIVE=ON' "$TEMP_DOCKERFILE"
	fi

	echo "$TEMP_DOCKERFILE"
}

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
	else
		# patch_for_native: force GGML_NATIVE=ON everywhere else
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

	# Cleanup temporary Dockerfile if used
	if [ "$USE_TEMP_DOCKERFILE" -eq 1 ] && [ -f "$TEMP_DOCKERFILE" ]; then
		rm -f "$TEMP_DOCKERFILE"
	fi
}

build_image "$IMAGE_TAG" "$DOCKERFILE" "$CONTEXT" "$EXTRA_ARGS"
