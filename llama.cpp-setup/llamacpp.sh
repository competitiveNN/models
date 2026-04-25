MODELS_PATH="$HOME/data/models/gguf"
DEVICES="--device /dev/dri/card0 --device /dev/dri/renderD128 --device /dev/dri/card1 --device /dev/dri/renderD129 --device /dev/accel"
APIKEY=abc
IMAGE="llama-cpp-intel"
MODE="bench"

qwen35_08b="/models/Qwen3.5-0.8B-GGUF/Qwen3.5-0.8B-UD-Q4_K_XL.gguf"
qwen3_4b="/models/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
qwen3_8b="/models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf"
qwen35_9b="/models/Qwen3.5-9B-GGUF/Qwen3.5-9B-UD-Q4_K_XL.gguf"
qwen35_122b="/models/Qwen3.5-122B-A10B-GGUF/UD-Q4_K_XL/Qwen3.5-122B-A10B-UD-Q4_K_XL-00001-of-00003.gguf"
qwen36_35b_moe="/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
qwen36_27b="/models/Qwen3.6-27B-GGUF/Qwen3.6-27B-UD-Q4_K_XL.gguf"

gemma4_31b="/models/gemma-4-31B-it-GGUF/gemma-4-31B-it-UD-Q4_K_XL.gguf"
gemma4_26b_a4b="/models/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf"

lfm2_24b="/models/LFM2-24B-A2B-GGUF/LFM2-24B-A2B-Q4_K_M.gguf"
lfm25_1_2b="/models/LFM2.5-1.2B-Instruct-GGUF/LFM2.5-1.2B-Instruct-UD-Q4_K_XL.gguf"

hypernova_60b="/models/Hypernova-60B-2602-GGUF/Hypernova-60B-2602-GGUF.gguf" # 8tps
phi3_2b="/models/Phi-3-mini-4k-instruct-gguf/Phi-3-mini-4k-instruct-q4.gguf"

MODEL=$qwen36_35b_moe

SPEC_DRAFT_MODEL="" # $qwen35_08b
SPEC_DRAFT_MAX="${SPEC_DRAFT_MAX:-48}"
SPEC_DRAFT_MIN="${SPEC_DRAFT_MIN:-12}"
SPEC_TYPE="${SPEC_TYPE:-ngram-map-k}"
SPEC_NGRAM_SIZE_N="${SPEC_NGRAM_SIZE_N:-24}"

N_GPU_LAYERS="${N_GPU_LAYERS:-}"
SELECTED_GPUS=()
N_CPU_MOE="${N_CPU_MOE:-0}"
DETECT="${DETECT:-}"
PRESERVE_THINKING="${PRESERVE_THINKING:-}"

usage() {
	echo "Usage: $0 [--intel|--vulkan|--cpu|--ik] [server|--bench] [options] [-- <extra llama.cpp args>]"
	echo "  --cpu                     Run in CPU mode (no GPU devices, --n-gpu-layers 0)"
	echo "  --ik                      Run with ik_llama CPU image"
	echo "  --ngl N                   Number of GPU layers (default: 9999 for GPU, 0 for CPU)"
	echo "  --moe N                   Number of CPU MOE layers (default: 0)"
	echo "  --detect                  Automatically detect memory and infer --n-gpu-layers"
	echo "  --pthinking                Enable preserve_thinking in chat template (sets --chat-template-kwargs '{\"preserve_thinking\":true}')"
	echo "  --spec-ngram-size-n N       Set ngram size for ngram spec decoding (e.g., 24)"
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

    # Determine number of layers by reading model metadata
    MODEL_DIR="${HOST_MODEL_PATH%/*}"  # Get directory containing the model file
    README_FILE="$MODEL_DIR/README.md"

    if [[ -f "$README_FILE" ]]; then
        # Try to extract layer count from README.md
        NUM_LAYERS=$(grep -i "Number of Layers:" "$README_FILE" | sed 's/.*: *\([0-9]*\).*/\1/' | head -1)
        if [[ -n "$NUM_LAYERS" && "$NUM_LAYERS" =~ ^[0-9]+$ ]]; then
            echo "Found layer count in README: $NUM_LAYERS" >&2
        else
            NUM_LAYERS=""
        fi
    fi

    # Fallback: try to estimate from model size and typical layer sizes
    if [[ -z "$NUM_LAYERS" ]]; then
        # Rough estimation based on model size (MB) and typical layer sizes
        # Most models have layers around 300-600MB each for Q4_K quantizations
        AVG_LAYER_SIZE_MB=400  # Conservative estimate
        ESTIMATED_LAYERS=$((MODEL_SIZE_MB / AVG_LAYER_SIZE_MB))

        # Clamp to reasonable bounds
        if ((ESTIMATED_LAYERS < 10)); then
            NUM_LAYERS=10
        elif ((ESTIMATED_LAYERS > 200)); then
            NUM_LAYERS=200
        else
            NUM_LAYERS=$ESTIMATED_LAYERS
        fi

        echo "Warning: Could not find layer count in metadata, estimating $NUM_LAYERS layers from model size" >&2
    fi

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
	--pthinking)
		PRESERVE_THINKING=1
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
	--spec-ngram-size-n)
		[[ -n "${2:-}" ]] || die "error: --spec-ngram-size-n requires a value"
		SPEC_NGRAM_SIZE_N="$2"
		shift 2
		;;
	--help)
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
if [[ -n "$SPEC_DRAFT_MODEL" ]] && [[ "$SPEC_DRAFT_MODEL" != "1" ]] && [[ "$SPEC_DRAFT_MODEL" != /* ]]; then
	die "error: SPEC_DRAFT_MODEL/--draft-model must be an absolute path inside the container (e.g. /models/...) or 1 for spec decoding without draft model"
fi

if [[ -n "$DETECT" ]] && [[ -z "$CPU_MODE" ]]; then
    calculate_ngl
    echo "Detected optimal N_GPU_LAYERS: $N_GPU_LAYERS"
    echo "Use: ./llamacpp.sh --intel --ngl $N_GPU_LAYERS [other options]"
    exit 0
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

# Function to parse context size with k/m suffixes
parse_ctx_size() {
	local value="$1"
	if [[ "$value" =~ ^([0-9]+)([km]?)$ ]]; then
		local num="${BASH_REMATCH[1]}"
		local suffix="${BASH_REMATCH[2]}"
		case "$suffix" in
			k|K) echo $((num * 1024)) ;;
			m|M) echo $((num * 1024 * 1024)) ;;
			*) echo "$num" ;;
		esac
	else
		echo "$value"
	fi
}

MODEL_ARGS=(-m "$MODEL")

# Check if --fit-ctx or --fit-target are present in arguments
USE_FIT_MODE=0
FIT_CTX_SIZE=""
MANUAL_CTX_SIZE=""
for ((i=1; i<=$#; i++)); do
	arg="${!i}"
	if [[ "$arg" == "--fit-ctx" ]]; then
		USE_FIT_MODE=1
		next_i=$((i + 1))
		if ((next_i <= $#)); then
			next_arg="${!next_i}"
			if [[ "$next_arg" != -* ]]; then
				FIT_CTX_SIZE="$(parse_ctx_size "$next_arg")"
			fi
		fi
	elif [[ "$arg" == "--fit-target" ]] || [[ "$arg" == "--fitt" ]]; then
		USE_FIT_MODE=1
	elif [[ "$arg" == "--ctx-size" ]] || [[ "$arg" == "-c" ]]; then
		next_i=$((i + 1))
		if ((next_i <= $#)); then
			next_arg="${!next_i}"
			if [[ "$next_arg" != -* ]]; then
				MANUAL_CTX_SIZE="$(parse_ctx_size "$next_arg")"
			fi
		fi
	fi
done


if [[ $USE_FIT_MODE -eq 0 ]]; then
	if [[ -z "$CPU_MODE" ]]; then
		if [[ -n "$N_GPU_LAYERS" ]]; then
			MODEL_ARGS+=(--n-gpu-layers "$N_GPU_LAYERS")
		fi
	else
		MODEL_ARGS+=(--n-gpu-layers 0)
	fi

	MODEL_ARGS+=(--n-cpu-moe "$N_CPU_MOE")
fi

# Set ctx-size: manual > fit-ctx > default
if [[ -n "$MANUAL_CTX_SIZE" ]]; then
	MODEL_ARGS+=(--ctx-size "$MANUAL_CTX_SIZE")
elif [[ -n "$FIT_CTX_SIZE" ]]; then
	MODEL_ARGS+=(--ctx-size "$FIT_CTX_SIZE")
elif [[ $USE_FIT_MODE -eq 0 ]]; then
	MODEL_ARGS+=(--ctx-size 16384)
fi
MODEL_ARGS+=(--threads 8)

if [[ -n "$CPU_MODE" ]]; then
	MODEL_ARGS=(
		-m "$MODEL"
		--n-gpu-layers 0
	)
	if [[ -n "$MANUAL_CTX_SIZE" ]]; then
		MODEL_ARGS+=(--ctx-size "$MANUAL_CTX_SIZE")
	elif [[ -n "$FIT_CTX_SIZE" ]]; then
		MODEL_ARGS+=(--ctx-size "$FIT_CTX_SIZE")
	elif [[ $USE_FIT_MODE -eq 0 ]]; then
		MODEL_ARGS+=(--ctx-size 16384)
	fi
	MODEL_ARGS+=(--threads 8)
	# Disable SYCL backends that require GPU hardware
	DOCKER_ARGS+=(-e GGML_BACKEND=cpu)
fi

SPEC_ARGS=()
if [[ -n "$SPEC_DRAFT_MODEL" && "$SPEC_DRAFT_MODEL" != "1" ]]; then
	SPEC_ARGS+=(--model-draft "$SPEC_DRAFT_MODEL")
fi
# If SPEC_DRAFT_MODEL is "1", skip --model-draft but still allow other spec args
if [[ -n "$SPEC_DRAFT_MAX" ]]; then
	SPEC_ARGS+=(--draft-max "$SPEC_DRAFT_MAX")
fi
if [[ -n "$SPEC_DRAFT_MIN" ]]; then
	SPEC_ARGS+=(--draft-min "$SPEC_DRAFT_MIN")
fi
if [[ -n "$SPEC_TYPE" ]]; then
	SPEC_ARGS+=(--spec-type "$SPEC_TYPE")
fi
if [[ -n "$SPEC_NGRAM_SIZE_N" ]]; then
	SPEC_ARGS+=(--spec-ngram-size-n "$SPEC_NGRAM_SIZE_N")
fi

DOCKER_ARGS=("${COMMON_ARGS[@]}")
CMD_ARGS=("${MODEL_ARGS[@]}")

if [[ "$MODE" == "server" ]]; then
	echo "Running in server mode..."
	DOCKER_ARGS+=(-p 8000:8000)
	# Append server-specific args
	CMD_ARGS=("${CMD_ARGS[@]}" "${SPEC_ARGS[@]}" --host 0.0.0.0 --port 8000)
else
	echo "Running in benchmark mode..."
	# Override entrypoint to llama-bench
	DOCKER_ARGS+=(--entrypoint /app/llama-bench)
	# Set bench-specific args
	CMD_ARGS=(-m "$MODEL")
	if [[ $USE_FIT_MODE -eq 0 && -n "$N_GPU_LAYERS" ]]; then
		CMD_ARGS+=(--n-gpu-layers "$N_GPU_LAYERS")
	fi
	if [[ -n "$PRESERVE_THINKING" ]]; then
		CMD_ARGS+=(--chat-template-kwargs '{"preserve_thinking": true}')
	fi
fi

# Strip processed arguments from extra args
clean_args=()
skip_next=0
for arg in "$@"; do
	if ((skip_next > 0)); then
		((skip_next--))
		continue
	fi

	case "$arg" in
		"bench"|"--bench")
			# Skip in bench mode
			if [[ "$MODE" == "bench" ]]; then
				continue
			fi
			;;
		"--ctx-size"|"-c"|"--fit-ctx"|"--fit-target"|"--fitt")
			# Skip these arguments and their values as they're processed
			skip_next=1
			continue
			;;
	esac
	clean_args+=("$arg")
done
set -- "${clean_args[@]}"

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
