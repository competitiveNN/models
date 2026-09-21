#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

MODEL_PATH="$HOME/data/models/ov"
DEVICES="--device /dev/accel:/dev/accel --device /dev/dri/card0:/dev/dri/card0 --device /dev/dri/renderD128:/dev/dri/renderD128 --device /dev/dri/card1:/dev/dri/card1 --device /dev/dri/renderD129:/dev/dri/renderD129"
MODEL=""

# Check if container is running
if ! docker ps --filter "name=openarc" --format "{{.Names}}" | grep -q "openarc"; then
    echo "Error: openarc container is not running"
    echo "Please start the container first with: $SCRIPT_DIR/openarc.sh"
    exit 1
fi

ENGINE="ovgenai"
MODEL_TYPE="vlm"
DEVICE="HETERO:GPU.1,GPU.0"
RUNTIME_CONFIG='{"PERFORMANCE_HINT": "CUMULATIVE_THROUGHPUT", "KV_CACHE_PRECISION": "u8", "MODEL_DISTRIBUTION_POLICY": "PIPELINE_PARALLEL"}'
DRAFT_DEVICE="HETERO:GPU.1,GPU.0"
NUM_ASSISTANT_TOKENS=10
ASSISTANT_CONFIDENCE_THRESHOLD=0.5

#BASE_PATH="$HOME/data/models/ov"
BASE_PATH="/models"
qwen3_6l06b="$BASE_PATH/Qwen3-pruned-6L-from-0.6B-int8-ov/"
qwen36_35ba3b="$BASE_PATH/Qwen3.6-35b-a3b-int4-ov/"
qwen36_27b="$BASE_PATH/Qwen3.6-27B-int4-ov/"
qwen38_27b="$BASE_PATH/Qwen3.8-27B-int4-ov/"
ornith15_9b="$BASE_PATH/Ornith-1.5-9B-int4_asym-awq-ov/"
lfm_12b="$BASE_PATH/LFM2.5-1.2B-Thinking-int4_asym-ov/"
muse_glimmer_30b="$BASE_PATH/Muse-Glimmer-30B-int4-ov/"

nemotron_14b="$BASE_PATH/Nemotron-Cascade-14B-Thinking-int4_asym-se-ov/"
nousc_14b="$BASE_PATH/NousCoder-14B-int4_sym-ov/"

MODEL_PATH=$muse_glimmer_30b
DRAFT_MODEL_PATH="" # $qwen3_6l06b
MODEL_NAME="model"

ARGS=(
	--mn "${MODEL_NAME}"
	--m "${MODEL_PATH}"
	--engine "${ENGINE}"
	--mt "${MODEL_TYPE}"
	--device "${DEVICE}"
	--runtime-config "${RUNTIME_CONFIG}"
)

if [[ -n "${DRAFT_MODEL_PATH}" ]]; then
	ARGS+=(
		--draft-model-path "${DRAFT_MODEL_PATH}"
		--draft-device "${DRAFT_DEVICE}"
		--num-assistant-tokens "${NUM_ASSISTANT_TOKENS}"
		--assistant-confidence-threshold "${ASSISTANT_CONFIDENCE_THRESHOLD}"
	)
fi

echo "${ARGS[@]}"
docker exec openarc openarc add "${ARGS[@]}"
docker exec openarc openarc unload $MODEL_NAME
docker exec openarc openarc load $MODEL_NAME
