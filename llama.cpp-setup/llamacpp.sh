MODELS_PATH="$HOME/data/models/gguf"
DEVICES="--device /dev/dri/card0 --device /dev/dri/renderD128 --device /dev/dri/card1 --device /dev/dri/renderD129 --device /dev/accel"
APIKEY=abc
IMAGE="llama-cpp-intel"
MODE="bench"

qwen35_08b="/models/Qwen3.5-0.8B-GGUF/Qwen3.5-0.8B-UD-Q4_K_XL.gguf"
qwen3_4b="/models/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
qwen3_8b="/models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf"
qwen35_9b="/models/Qwen3.5-9B-GGUF/Qwen3.5-9B-UD-Q4_K_XL.gguf"
qwen35_27b="/models/Qwen3.5-27B-GGUF/Qwen3.5-27B-UD-Q4_K_XL.gguf"
qwen35_122b="/models/Qwen3.5-122B-A10B-GGUF/UD-Q4_K_XL/Qwen3.5-122B-A10B-UD-Q4_K_XL-00001-of-00003.gguf"
qwen36_35b_moe="/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
glm_47_flash_23b="/models/GLM-4.7-Flash/GLM-4.7-Flash-REAP-23B-A3B-UD-Q4_K_XL.gguf"
phi3_mini="/models/Phi-3-mini-4k-instruct-gguf/Phi-3-mini-4k-instruct-q4.gguf"
gemma4_31b="/models/gemma-4-31B-it-GGUF/gemma-4-31B-it-UD-Q4_K_XL.gguf"
gemma4_26b_a4b="/models/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf"

ministral3_3b="/models/Ministral-3-3B-Instruct-2512-GGUF/Ministral-3-3B-Instruct-2512-UD-IQ2_XXS.gguf"
ministral3_8b="/models/Ministral-3-8B-Instruct-2512-GGUF/Ministral-3-8B-Instruct-2512-UD-Q4_K_XL.gguf"

lfm2_24b="/models/LFM2-24B-A2B-GGUF/LFM2-24B-A2B-Q4_K_M.gguf"
lfm25_1_2b="/models/LFM2.5-1.2B-Instruct-GGUF/LFM2.5-1.2B-Instruct-UD-Q4_K_XL.gguf"

hypernova_60b="/models/Hypernova-60B-2602-GGUF/Hypernova-60B-2602-GGUF.gguf" # 8tps
phi3_2b="/models/Phi-3-mini-4k-instruct-gguf/Phi-3-mini-4k-instruct-q4.gguf"

MODEL=$qwen36_35b_moe

SPEC_DRAFT_MODEL="" # $qwen35_08b
SPEC_DRAFT_MAX="${SPEC_DRAFT_MAX:-}"
SPEC_DRAFT_MIN="${SPEC_DRAFT_MIN:-}"
SPEC_TYPE="${SPEC_TYPE:-}"

N_GPU_LAYERS="${N_GPU_LAYERS:-}"
SELECTED_GPUS=()
N_CPU_MOE="${N_CPU_MOE:-0}"
DETECT="${DETECT:-}"

usage() {
	echo "Usage: $0 [--intel|--vulkan|--cpu|--ik] [server|--bench] [options] [-- <extra llama.cpp args>]"
	echo "  --cpu                     Run in CPU mode (no GPU devices, --n-gpu-layers 0)"
	echo "  --ik                      Run with ik_llama CPU image"
	echo "  --ngl N                   Number of GPU layers (default: 9999 for GPU, 0 for CPU)"
	echo "  --moe N                   Number of CPU MOE layers (default: 0)"
	echo "  --detect                  Automatically detect memory and infer --n-gpu-layers"
}

die() {
	echo "$1" >&2
	echo >&2
	usage >&2
	exit 2
}

is_uint() {
	[[ "$1" =~ ^[0-9]+$ ]]
}

calculate_ngl() {
	# Automatic memory detection
	NUM_GPUS=2
	GPU_VRAM_MB=12216   # Actual from device info
	SYSTEM_RAM_MB=65536 # 64GB system RAM
	# Get model file path on host
	HOST_MODEL_PATH="${MODELS_PATH}${MODEL#/models}"
	MODEL_SIZE_BYTES=$(stat -f%z "$HOST_MODEL_PATH" 2>/dev/null || du -b "$HOST_MODEL_PATH" 2>/dev/null | cut -f1 || echo 0)
	MODEL_SIZE_MB=$((MODEL_SIZE_BYTES / 1024 / 1024))
	# From model info: 60 layers
	NUM_LAYERS=60
	LAYER_SIZE_MB=$((MODEL_SIZE_MB / NUM_LAYERS))
	# Estimate initial NGL without KV
	INITIAL_TOTAL_MB=$((GPU_VRAM_MB * NUM_GPUS - 1024)) # 1GB margin for other
	NGL=$((INITIAL_TOTAL_MB / LAYER_SIZE_MB))
	if ((NGL > NUM_LAYERS)); then NGL=$NUM_LAYERS; fi
	# Estimate KV cache size (scales with context, based on 1280 MiB for 16384 ctx and 10 layers)
	KV_MB=$((1280 * NGL / 10))
	# Recalculate with KV
	TOTAL_GPU_MB=$((GPU_VRAM_MB * NUM_GPUS - KV_MB - 1024))
	NGL=$((TOTAL_GPU_MB / LAYER_SIZE_MB))
	if ((NGL > NUM_LAYERS)); then NGL=$NUM_LAYERS; fi
	if ((NGL < 1)); then NGL=1; fi
	N_GPU_LAYERS=$NGL
}

while [[ "$#" -gt 0 ]]; do
	case $1 in
	--vulkan)
		IMAGE="llama-cpp-vulkan"
		shift
		;;
	--intel)
		IMAGE="llama-cpp-intel"
		shift
		;;
	--ov | --openvino)
		IMAGE="llama-cpp-openvino"
		shift
		;;
	--cpu)
		CPU_MODE=1
		IMAGE="llama-cpp-intel"
		N_GPU_LAYERS=0
		shift
		;;
	--ik)
		IMAGE="ik-llama-cpu"
		DEVICES=""
		CPU_MODE=1
		N_GPU_LAYERS=0
		shift
		;;
	--ngl)
		[[ -n "${2:-}" ]] || die "error: --ngl requires a value"
		N_GPU_LAYERS="$2"
		shift 2
		;;
	--moe)
		[[ -n "${2:-}" ]] || die "error: --moe requires a value"
		N_CPU_MOE="$2"
		shift 2
		;;
	--detect)
		DETECT=1
		shift
		;;
	--gpus)
		[[ -n "${2:-}" ]] || die "error: --gpus requires a value (e.g., 0,1 or 0)"
		IFS=',' read -ra SELECTED_GPUS <<<"$2"
		shift 2
		;;
	server)
		MODE="server"
		shift
		;;
	--bench)
		MODE="bench"
		shift
		;;
	--draft-model)
		[[ -n "${2:-}" ]] || die "error: --draft-model requires a value"
		SPEC_DRAFT_MODEL="$2"
		shift 2
		;;
	--draft-max)
		[[ -n "${2:-}" ]] || die "error: --draft-max requires a value"
		SPEC_DRAFT_MAX="$2"
		shift 2
		;;
	--draft-min)
		[[ -n "${2:-}" ]] || die "error: --draft-min requires a value"
		SPEC_DRAFT_MIN="$2"
		shift 2
		;;
	--spec-type)
		[[ -n "${2:-}" ]] || die "error: --spec-type requires a value"
		SPEC_TYPE="$2"
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	*) break ;;
	esac
done

if [[ -n "$SPEC_DRAFT_MAX" ]] && ! is_uint "$SPEC_DRAFT_MAX"; then
	die "error: SPEC_DRAFT_MAX/--draft-max must be an integer"
fi
if [[ -n "$SPEC_DRAFT_MIN" ]] && ! is_uint "$SPEC_DRAFT_MIN"; then
	die "error: SPEC_DRAFT_MIN/--draft-min must be an integer"
fi
if [[ -n "$N_GPU_LAYERS" ]] && ! is_uint "$N_GPU_LAYERS"; then
	die "error: --ngl must be an integer"
fi
if [[ -n "$N_CPU_MOE" ]] && ! is_uint "$N_CPU_MOE"; then
	die "error: --moe must be an integer"
fi
if [[ -n "$SPEC_DRAFT_MODEL" ]] && [[ "$SPEC_DRAFT_MODEL" != /* ]]; then
	die "error: SPEC_DRAFT_MODEL/--draft-model must be an absolute path inside the container (e.g. /models/...)"
fi

if [[ -n "$DETECT" ]] && [[ -z "$CPU_MODE" ]]; then
	calculate_ngl
fi

# Build DEVICES from SELECTED_GPUS; default to both if empty
if ((${#SELECTED_GPUS[@]} == 0)); then
	SELECTED_GPUS=(0 1)
fi
DEVICES=""
for gpu in "${SELECTED_GPUS[@]}"; do
	case "$gpu" in
	0) DEVICES+="--device /dev/dri/card0 --device /dev/dri/renderD128 " ;;
	1) DEVICES+="--device /dev/dri/card1 --device /dev/dri/renderD129 " ;;
	*) echo "Warning: Unknown GPU index $gpu, skipping" >&2 ;;
	esac
done
DEVICES+="--device /dev/accel"

COMMON_ARGS=(
	--security-opt label=disable
	-it --rm
	-v "$MODELS_PATH":/models
	${DEVICES:-}
)

MODEL_ARGS=(-m "$MODEL")

if [[ -z "$CPU_MODE" ]]; then
	if [[ -n "$N_GPU_LAYERS" ]]; then
		MODEL_ARGS+=(--n-gpu-layers "$N_GPU_LAYERS")
	fi
else
	MODEL_ARGS+=(--n-gpu-layers 0)
fi

MODEL_ARGS+=(--n-cpu-moe "$N_CPU_MOE" --ctx-size 16384 --threads 8)

if [[ -n "$CPU_MODE" ]]; then
	MODEL_ARGS=(
		-m "$MODEL"
		--n-gpu-layers 0
		--ctx-size 16384
		--threads 8
	)
	# Disable SYCL backends that require GPU hardware
	DOCKER_ARGS+=(-e GGML_BACKEND=cpu)
fi

SPEC_ARGS=()
if [[ -n "$SPEC_DRAFT_MODEL" ]]; then
	SPEC_ARGS+=(--model-draft "$SPEC_DRAFT_MODEL")
fi
if [[ -n "$SPEC_DRAFT_MAX" ]]; then
	SPEC_ARGS+=(--draft-max "$SPEC_DRAFT_MAX")
fi
if [[ -n "$SPEC_DRAFT_MIN" ]]; then
	SPEC_ARGS+=(--draft-min "$SPEC_DRAFT_MIN")
fi
if [[ -n "$SPEC_TYPE" ]]; then
	SPEC_ARGS+=(--spec-type "$SPEC_TYPE")
fi

DOCKER_ARGS=("${COMMON_ARGS[@]}")
CMD_ARGS=("${MODEL_ARGS[@]}" "${SPEC_ARGS[@]}")

if [[ "$MODE" == "server" ]]; then
	echo "Running in server mode..."
	DOCKER_ARGS+=(-p 8000:8000)
	# Append server-specific args
	CMD_ARGS=("${CMD_ARGS[@]}" --host 0.0.0.0 --port 8000)
else
	echo "Running in benchmark mode..."
	# Override entrypoint to llama-bench
	DOCKER_ARGS+=(--entrypoint /app/llama-bench)
	# Set bench-specific args
	CMD_ARGS=(-m "$MODEL" "${SPEC_ARGS[@]}")
	if [[ -n "$N_GPU_LAYERS" ]]; then
		CMD_ARGS+=(--n-gpu-layers "$N_GPU_LAYERS")
	fi
fi

# Strip 'bench' or '--bench' from extra args if in bench mode
if [[ "$MODE" == "bench" ]]; then
	clean_args=()
	for arg in "$@"; do
		if [[ "$arg" != "bench" && "$arg" != "--bench" ]]; then
			clean_args+=("$arg")
		fi
	done
	set -- "${clean_args[@]}"
fi

# Print the command passed to llama.cpp
if [[ "$MODE" == "server" ]]; then
	printf "llama-server command:"
	printf " %q" "${CMD_ARGS[@]}" "$@"
	printf "\n"
else
	printf "llama-bench command:"
	printf " %q" "${CMD_ARGS[@]}" "$@"
	printf "\n"
fi

docker run "${DOCKER_ARGS[@]}" \
	"$IMAGE" \
	"${CMD_ARGS[@]}" \
	"$@"
