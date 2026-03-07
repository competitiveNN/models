MODELS_PATH="$HOME/data/models/gguf"
#MODEL="/models/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
#MODEL="/models/Hypernova-60B-2602-GGUF/Hypernova-60B-2602-GGUF.gguf"
MODEL="/models/unsloth/Qwen3.5-35B-A3B-GGUF-UD-Q4_K_XL/Qwen3.5-35B-A3B-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Magistral-Small-2509-GGUF-UD-Q4_K_XL/Magistral-Small-2509-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Magistral-Small-2509-GGUF-UD-Q4_K_XL/Magistral-Small-2509-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF-UD-Q4_K_XL/Mistral-Small-3.2-24B-Instruct-2506-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF-UD-Q4_K_XL/Devstral-Small-2-24B-Instruct-2512-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Magistral-Small-2509-GGUF-UD-Q4_K_XL/Magistral-Small-2509-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Ministral-3-8B-Instruct-2512-GGUF-UD-Q4_K_XL/Ministral-3-8B-Instruct-2512-UD-Q4_K_XL.gguf"

DEVICES="--device /dev/dri/card0 --device /dev/dri/renderD128 --device /dev/dri/card1 --device /dev/dri/renderD129 --device /dev/accel"
APIKEY=abc
IMAGE="llama-cpp-intel"
MODE="bench"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --vulkan) IMAGE="llama-cpp-vulkan"; shift ;;
        --intel) IMAGE="llama-cpp-intel"; shift ;;
        server) MODE="server"; shift ;;
        --bench) MODE="bench"; shift ;;
        *) break ;;
    esac
done

COMMON_ARGS=(
    --security-opt label=disable
    -it --rm
    -v "$MODELS_PATH":/models
    $DEVICES
)

MODEL_ARGS=(
    -m "$MODEL"
    #--n-gpu-layers 0
    #--n-cpu-moe 99
    --ctx-size 2048
    --threads 20
    --n-predict -1
)

DOCKER_ARGS=("${COMMON_ARGS[@]}")
CMD_ARGS=("${MODEL_ARGS[@]}")

if [[ "$MODE" == "server" ]]; then
    echo "Running in server mode..."
    DOCKER_ARGS+=(-p 8000:8000)
    # Prepend llama-server and append server-specific args
    CMD_ARGS=(--server "${CMD_ARGS[@]}" --host 0.0.0.0 --port 8000)
else
    echo "Running in benchmark mode..."
    # Prepend --bench
    CMD_ARGS=(--bench "${CMD_ARGS[@]}")
fi

docker run "${DOCKER_ARGS[@]}" \
    "$IMAGE" \
    "${CMD_ARGS[@]}" \
    "$@"
