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
qwen35_35b="/models/Qwen3.5-35B-A3B-GGUF/Qwen3.5-35B-A3B-UD-Q4_K_XL.gguf" # 8tps
qwen3c_80b="/models/Qwen3-Coder-Next-GGUF/Qwen3-Coder-Next-UD-TQ1_0.gguf" # 8 tps
qwen35_122b="/models/Qwen3.5-122B-A10B-GGUF/UD-Q4_K_XL/Qwen3.5-122B-A10B-UD-Q4_K_XL-00001-of-00003.gguf"

ministral3_3b="/models/Ministral-3-3B-Instruct-2512-GGUF/Ministral-3-3B-Instruct-2512-UD-IQ2_XXS.gguf"
ministral3_8b="/models/Ministral-3-8B-Instruct-2512-GGUF/Ministral-3-8B-Instruct-2512-UD-Q4_K_XL.gguf"
devstral2_24b="/models/Devstral-Small-2-24B-Instruct-2512-GGUF/Devstral-Small-2-24B-Instruct-2512-UD-Q4_K_XL.gguf"
mistral32_24b="/models/Mistral-Small-3.2-24B-Instruct-2506-GGUF/Mistral-Small-3.2-24B-Instruct-2506-UD-Q4_K_XL.gguf"

lfm2_24b="/models/LFM2-24B-A2B-GGUF/LFM2-24B-A2B-Q4_K_M.gguf"
lfm25_1_2b="/models/LFM2.5-1.2B-Instruct-GGUF/LFM2.5-1.2B-Instruct-UD-Q4_K_XL.gguf"

hypernova_60b="/models/Hypernova-60B-2602-GGUF/Hypernova-60B-2602-GGUF.gguf" # 8tps
phi3_2b="/models/Phi-3-mini-4k-instruct-gguf/Phi-3-mini-4k-instruct-q4.gguf"

MODEL=$qwen35_35b

SPEC_DRAFT_MODEL="" # $qwen35_08b
SPEC_DRAFT_MAX="${SPEC_DRAFT_MAX:-}"
SPEC_DRAFT_MIN="${SPEC_DRAFT_MIN:-}"
SPEC_TYPE="${SPEC_TYPE:-}"

usage() {
	echo "Usage: $0 [--intel|--vulkan|--cpu] [server|--bench] [speculative options] [-- <extra llama.cpp args>]"
	echo "  --cpu                     Run in CPU mode (no GPU devices, --n-gpu-layers 0)"
	echo "Speculative decoding options:"
	echo "  --draft-model PATH        Draft model GGUF path inside container (e.g. /models/...)"
	echo "  --draft-max N             Max draft tokens (llama.cpp: --draft-max)"
	echo "  --draft-min N             Min draft tokens (llama.cpp: --draft-min)"
	echo "  --spec-type TYPE          Draftless spec type (e.g. ngram-simple, ngram-mod, ...)"
	echo "Environment equivalents: SPEC_DRAFT_MODEL, SPEC_DRAFT_MAX, SPEC_DRAFT_MIN, SPEC_TYPE"
	echo "Defaults: if MODEL looks like Qwen and no speculative options are set, we use --spec-type ngram-mod --draft-min 8 --draft-max 32"
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
	--ov)
		IMAGE="llama-cpp-openvino"
		shift
		;;
	--cpu)
		CPU_MODE=1
		shift
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
if [[ -n "$SPEC_DRAFT_MODEL" ]] && [[ "$SPEC_DRAFT_MODEL" != /* ]]; then
	die "error: SPEC_DRAFT_MODEL/--draft-model must be an absolute path inside the container (e.g. /models/...)"
fi

COMMON_ARGS=(
	--security-opt label=disable
	-it --rm
	-v "$MODELS_PATH":/models
	${DEVICES:-}
)

MODEL_ARGS=(
	-m "$MODEL"
	--n-gpu-layers 9999
	--n-cpu-moe 0
	--ctx-size 16384
	--threads 8
	#--n-predict -1
)

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
	# Prepend llama-server and append server-specific args
	CMD_ARGS=("${CMD_ARGS[@]}" --host 0.0.0.0 --port 8000)
else
	echo "Running in benchmark mode..."
	# Prepend --bench
	CMD_ARGS=(--bench "${CMD_ARGS[@]}")
fi

docker run "${DOCKER_ARGS[@]}" \
	"$IMAGE" \
	"${CMD_ARGS[@]}" \
	"$@"
