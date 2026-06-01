MODELS_PATH="$HOME/data/models/gguf"
DEVICES="--device /dev/dri/card0 --device /dev/dri/renderD128 --device /dev/dri/card1 --device /dev/dri/renderD129 --device /dev/accel"
APIKEY=abc
IMAGE="llama-cpp-intel"
MODE="bench"
EXTRA_ARGS=()

# Function to parse size values with k/m/g suffixes
parse_size_value() {
	local value="$1"
	if [[ "$value" =~ ^([0-9]+)([kmg]?)$ ]]; then
		local num="${BASH_REMATCH[1]}"
		local suffix="${BASH_REMATCH[2]}"
		case "$suffix" in
			k|K) echo $((num * 1024)) ;;
			m|M) echo $((num * 1024 * 1024)) ;;
			g|G) echo $((num * 1024 * 1024 * 1024)) ;;
			*) echo "$num" ;;
		esac
	else
		echo "$value"
	fi
}

# Function to parse context size with k/m suffixes (tokens)
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

is_uint() {
	[[ "$1" =~ ^[0-9]+$ ]]
}

usage() {
	echo "Usage: $0 [--intel|--vulkan|--cpu|--ik] [server|--bench] [options] [-- <extra llama.cpp args>]"
	echo "  --cpu                     Run in CPU mode (no GPU devices, --n-gpu-layers 0)"
	echo "  --ik                      Run with ik_llama CPU image"
	echo "  --ngl N                   Number of GPU layers (default: all)"
	echo "  --moe N                   Number of CPU MOE layers (default: 0)"
	echo "  --detect                  Automatically detect memory and infer --n-gpu-layers"
	echo "  --mtp                   Enable Multi-Token Prediction (speculative decoding via model's own MTP heads)"
	echo "  --no-spec               Disable speculative decoding"
	echo "  --pthinking                Enable preserve_thinking in chat template (sets --chat-template-kwargs '{\"preserve_thinking\":true}')"
	echo "  NGRAM_SIZE_N (env)          Ngram size for spec decoding (default: 24). Use type-specific flag like --spec-ngram-map-k-size-n"
	echo "  --draft-max|--spec-draft-n-max N     Maximum number of draft tokens (default: 48)"
	echo "  --draft-min|--spec-draft-n-min N     Minimum number of draft tokens (default: 12)"
	echo "  --timeout N               Execution timeout in seconds (default: 3600)"
}

die() {
	echo "$1" >&2
	echo >&2
	usage >&2
	exit 2
}

qwen35_08b="/models/Qwen3.5-0.8B-GGUF/Qwen3.5-0.8B-UD-Q4_K_XL.gguf"
qwen35_08b_iq2xxs="/models/Qwen3.5-0.8B-GGUF/Qwen3.5-0.8B-UD-IQ2_XXS.gguf"
qwen3_4b="/models/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
qwen3_8b="/models/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf"
qwen35_9b="/models/Qwen3.5-9B-GGUF/Qwen3.5-9B-UD-Q4_K_XL.gguf"
qwen35_122b="/models/Qwen3.5-122B-A10B-GGUF/UD-Q4_K_XL/Qwen3.5-122B-A10B-UD-Q4_K_XL-00001-of-00003.gguf"
qwen36_35b="/models/Qwen3.6-35B-A3B-MTP-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
qwen36_35b_q3="/models/Qwen3.6-35B-A3B-MTP-GGUF/Qwen3.6-35B-A3B-UD-Q3_K_XL.gguf"
qwen36_35b_bpw_419="/models/Qwen3.6-35B-A3B-MTP-GGUF/Qwen3.6-35B-A3B-IQ4_XS-4.19bpw.gguf"
qwen36_35b_bpw_397="/models/Qwen3.6-35B-A3B-MTP-GGUF/Qwen3.6-35B-A3B-IQ4_XS-3.97bpw.gguf"
qwen36_35b_bpw_353="/models/Qwen3.6-35B-A3B-MTP-GGUF/Qwen3.6-35B-A3B-IQ4_XS-3.53bpw.gguf"
qwen36_27b="/models/Qwen3.6-27B-MTP-GGUF/Qwen3.6-27B-UD-Q4_K_XL.gguf"
qwen36_27b_q3="/models/Qwen3.6-27B-MTP-GGUF/Qwen3.6-27B-UD-Q3_K_XL.gguf"
qwen36_27b_reap="/models/Qwen3.6-28B-REAP-i1-GGUF/Qwen3.6-28B-REAP.i1-Q4_K_M.gguf"
qwen36_27b_bart="/models/Qwen_Qwen3.6-27B-GGUF/Qwen_Qwen3.6-27B-Q4_K_M.gguf"

lfm2_24b="/models/LFM2-24B-A2B-GGUF/LFM2-24B-A2B-Q4_K_M.gguf"
lfm25_1_2b="/models/LFM2.5-1.2B-Instruct-GGUF/LFM2.5-1.2B-Instruct-UD-Q4_K_XL.gguf"

hypernova_60b="/models/Hypernova-60B-2602-GGUF/Hypernova-60B-2602-GGUF.gguf" # 8tps
gptoss_20b="/models/gpt-oss-20b-GGUF/gpt-oss-20b-UD-Q4_K_XL.gguf"
phi3_2b="/models/Phi-3-mini-4k-instruct-gguf/Phi-3-mini-4k-instruct-q4.gguf"

MODEL=$qwen36_27b_reap

SPEC_DRAFT_MODEL="" # $qwen35_08b
SPEC_DRAFT_MAX="${SPEC_DRAFT_MAX:-48}"
SPEC_DRAFT_MIN="${SPEC_DRAFT_MIN:-12}"
SPEC_DRAFT_KV_K="${SPEC_DRAFT_KV_K:-}"
SPEC_DRAFT_KV_V="${SPEC_DRAFT_KV_V:-}"
SPEC_TYPE="${SPEC_TYPE:-ngram-map-k}"
SPEC_NGRAM_SIZE_N="${SPEC_NGRAM_SIZE_N:-24}"

N_GPU_LAYERS="${N_GPU_LAYERS:-all}"
SELECTED_GPUS=()
N_CPU_MOE="${N_CPU_MOE:-0}"
MTP="${MTP:-}"
DETECT="${DETECT:-}"
PRESERVE_THINKING="${PRESERVE_THINKING:-}"
TIMEOUT="${TIMEOUT:-3600}"

while [[ "$#" -gt 0 ]]; do
	case $1 in
	--draft-model)
		[[ -n "${2:-}" ]] || die "error: --draft-model requires a value"
		SPEC_DRAFT_MODEL="$2"
		shift 2
		;;
	--timeout)
		[[ -n "${2:-}" ]] || die "error: --timeout requires a value"
		TIMEOUT="$2"
		shift 2
		;;
	--draft-max|--spec-draft-n-max)
		[[ -n "${2:-}" ]] || die "error: --draft-max/--spec-draft-n-max requires a value"
		SPEC_DRAFT_MAX="$2"
		shift 2
		;;
	--draft-min|--spec-draft-n-min)
		[[ -n "${2:-}" ]] || die "error: --draft-min/--spec-draft-n-min requires a value"
		SPEC_DRAFT_MIN="$2"
		shift 2
		;;
	--spec-type)
		[[ -n "${2:-}" ]] || die "error: --spec-type requires a value"
		SPEC_TYPE="$2"
		shift 2
		;;
	--spec-ngram-size-n)
		die "error: --spec-ngram-size-n is deprecated. Use type-specific flags: --spec-ngram-<type>-size-n (e.g. --spec-ngram-map-k-size-n for ngram-map-k type)"
		;;
	--spec-draft-type-k|-ctkd)
		[[ -n "${2:-}" ]] || die "error: --spec-draft-type-k/-ctkd requires a value"
		SPEC_DRAFT_KV_K="$2"
		shift 2
		;;
	--spec-draft-type-v|-ctvd)
		[[ -n "${2:-}" ]] || die "error: --spec-draft-type-v/-ctvd requires a value"
		SPEC_DRAFT_KV_V="$2"
		shift 2
		;;
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
  --mtp)
		MTP=1
		shift
		;;
  --no-spec)
		NO_SPEC=1
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
	--fit-ctx)
		USE_FIT_MODE=1
		EXTRA_ARGS+=("$1")
		if [[ -n "${2:-}" ]] && [[ "$2" != -* ]]; then
			FIT_CTX_SIZE="$(parse_ctx_size "$2")"
			EXTRA_ARGS+=("$FIT_CTX_SIZE")
			shift 2
		else
			EXTRA_ARGS+=("4096")
			shift
		fi
		;;
	--fit)
		USE_FIT_MODE=1
		EXTRA_ARGS+=("$1")
		if [[ -n "${2:-}" ]] && [[ "$2" != -* ]]; then
			EXTRA_ARGS+=("$2")
			shift 2
		else
			shift
		fi
		;;
	--fit-target|--fitt)
		USE_FIT_MODE=1
		EXTRA_ARGS+=("$1")
		if [[ -n "${2:-}" ]] && [[ "$2" != -* ]]; then
			# Check if value has suffix (k/m/g)
			if [[ "$2" =~ [kmgKMG]$ ]]; then
				# Has suffix, parse and convert to MiB
				size_bytes="$(parse_size_value "$2")"
				size_mib=$((size_bytes / 1024 / 1024))
			else
				# No suffix, treat as MiB already
				size_mib="$2"
			fi
			EXTRA_ARGS+=("$size_mib")
			shift 2
		else
			shift
		fi
		;;
	--ctx-size|-c)
		EXTRA_ARGS+=("$1")
		if [[ -n "${2:-}" ]] && [[ "$2" != -* ]]; then
			MANUAL_CTX_SIZE="$(parse_ctx_size "$2")"
			EXTRA_ARGS+=("$MANUAL_CTX_SIZE")
			shift 2
		else
			shift
		fi
		;;
	--help)
		usage
		exit 0
		;;
	*)
		# Collect unrecognized arguments
		EXTRA_ARGS+=("$1")
		shift
		;;
	esac
done

if [[ -n "$SPEC_DRAFT_MAX" ]] && ! is_uint "$SPEC_DRAFT_MAX"; then
	die "error: SPEC_DRAFT_MAX/--draft-max must be an integer"
fi
if [[ -n "$SPEC_DRAFT_MIN" ]] && ! is_uint "$SPEC_DRAFT_MIN"; then
	die "error: SPEC_DRAFT_MIN/--draft-min must be an integer"
fi
if [[ -n "$N_GPU_LAYERS" ]] && [[ "$N_GPU_LAYERS" != "all" ]] && ! is_uint "$N_GPU_LAYERS"; then
	die "error: --ngl must be an integer"
fi
if [[ -n "$N_CPU_MOE" ]] && ! is_uint "$N_CPU_MOE"; then
	die "error: --moe must be an integer"
fi
if [[ -n "$TIMEOUT" ]] && ! is_uint "$TIMEOUT"; then
	die "error: --timeout must be an integer"
fi
if [[ -n "$MTP" ]]; then
	SPEC_DRAFT_MODEL="1"
	SPEC_TYPE="draft-mtp"
	SPEC_DRAFT_MAX="${MTP_DRAFT_MAX:-3}"
	SPEC_DRAFT_MIN="${MTP_DRAFT_MIN:-0}"
	SPEC_DRAFT_KV_K="q4_0"
	SPEC_DRAFT_KV_V="q4_0"
	CACHE_TYPE_K_DRAFT="q8_0"
	CACHE_TYPE_V_DRAFT="q8_0"
	SPEC_DRAFT_P_MIN="0.75"
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

MODEL_ARGS=(-m "$MODEL" -b 2048 -ub 2048 -fa on --reasoning-budget 2048 --reasoning-budget-message "\nBased on the analysis above, here is the complete solution:" --no-mmap)




if [[ $USE_FIT_MODE -eq 0 ]]; then
if [[ -z "$CPU_MODE" ]]; then
    if [[ "$N_GPU_LAYERS" == "all" ]]; then
        MODEL_ARGS+=(--n-gpu-layers -1)
    elif [[ -n "$N_GPU_LAYERS" ]]; then
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
		--no-mmap
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
if [[ -n "$NO_SPEC" ]]; then
  # Skip all speculative decoding arguments
  :
else
  if [[ -n "$SPEC_DRAFT_MODEL" && "$SPEC_DRAFT_MODEL" != "1" ]]; then
    SPEC_ARGS+=(--model-draft "$SPEC_DRAFT_MODEL")
  fi
  if [[ -n "$SPEC_DRAFT_MAX" ]]; then
    SPEC_ARGS+=(--spec-draft-n-max "$SPEC_DRAFT_MAX")
  fi
  if [[ -n "$SPEC_DRAFT_MIN" ]]; then
    SPEC_ARGS+=(--spec-draft-n-min "$SPEC_DRAFT_MIN")
  fi
  if [[ -n "$SPEC_TYPE" ]]; then
    SPEC_ARGS+=(--spec-type "$SPEC_TYPE")
  fi
  if [[ -n "$SPEC_DRAFT_KV_K" ]]; then
    SPEC_ARGS+=(--spec-draft-type-k "$SPEC_DRAFT_KV_K")
  fi
  if [[ -n "$SPEC_DRAFT_KV_V" ]]; then
    SPEC_ARGS+=(--spec-draft-type-v "$SPEC_DRAFT_KV_V")
  fi
  if [[ -n "$SPEC_DRAFT_P_MIN" ]]; then
    SPEC_ARGS+=(--spec-draft-p-min "$SPEC_DRAFT_P_MIN")
  fi
  if [[ -n "$CACHE_TYPE_K_DRAFT" ]]; then
    SPEC_ARGS+=(--cache-type-k-draft "$CACHE_TYPE_K_DRAFT")
  fi
  if [[ -n "$CACHE_TYPE_V_DRAFT" ]]; then
    SPEC_ARGS+=(--cache-type-v-draft "$CACHE_TYPE_V_DRAFT")
  fi
  # Use type-specific ngram flag based on SPEC_TYPE
  if [[ -n "$SPEC_NGRAM_SIZE_N" ]] && [[ "$SPEC_TYPE" =~ ^ngram ]]; then
    case "$SPEC_TYPE" in
      ngram-simple)  SPEC_ARGS+=(--spec-ngram-simple-size-n "$SPEC_NGRAM_SIZE_N") ;;
      ngram-map-k)   SPEC_ARGS+=(--spec-ngram-map-k-size-n "$SPEC_NGRAM_SIZE_N") ;;
      ngram-map-k4v) SPEC_ARGS+=(--spec-ngram-map-k4v-size-n "$SPEC_NGRAM_SIZE_N") ;;
      ngram-mod)     SPEC_ARGS+=(--spec-ngram-mod-n-match "$SPEC_NGRAM_SIZE_N") ;;
      *) die "Unsupported SPEC_TYPE for ngram size: $SPEC_TYPE" ;;
    esac
  fi
fi

DOCKER_ARGS=("${COMMON_ARGS[@]}")
CMD_ARGS=("${MODEL_ARGS[@]}")

if [[ "$MODE" == "server" ]]; then
	echo "Running in server mode..."
	DOCKER_ARGS+=(-p 8000:8000)
	# Append server-specific args
	CMD_ARGS=("${CMD_ARGS[@]}" "${SPEC_ARGS[@]}" --host 0.0.0.0 --port 8000 "${EXTRA_ARGS[@]}")
else
	echo "Running in benchmark mode..."
	# Override entrypoint to llama-bench
	DOCKER_ARGS+=(--entrypoint /app/llama-bench)
  # Set bench-specific args
  CMD_ARGS=(-m "$MODEL" -b 2048 -ub 512 --reasoning-budget 8192 --reasoning-budget-message "\nBased on the analysis above, here is the complete solution:")
if [[ $USE_FIT_MODE -eq 0 && -n "$N_GPU_LAYERS" ]] && [[ "$N_GPU_LAYERS" != "all" ]]; then
    CMD_ARGS+=(--n-gpu-layers "$N_GPU_LAYERS")
	fi
	if [[ -n "$PRESERVE_THINKING" ]]; then
		CMD_ARGS+=(--chat-template-kwargs '{"preserve_thinking": true}')
	fi
	CMD_ARGS+=("${EXTRA_ARGS[@]}")
fi



# Print the command passed to llama.cpp
if [[ "$MODE" == "server" ]]; then
	printf "timeout %s llama-server command:" "$TIMEOUT"
	printf " %q" "${CMD_ARGS[@]}"
	printf "\n"
else
	printf "timeout %s llama-bench command:" "$TIMEOUT"
	printf " %q" "${CMD_ARGS[@]}"
	printf "\n"
fi

timeout "$TIMEOUT" docker run "${DOCKER_ARGS[@]}" \
	"$IMAGE" \
	"${CMD_ARGS[@]}"
