#!/bin/bash

ENGINE="ovgenai"
MODEL_TYPE="llm"
DEVICE="HETERO:GPU.0,GPU.1"
RUNTIME_CONFIG='{"PERFORMANCE_HINT": "CUMULATIVE_THROUGHPUT", "KV_CACHE_PRECISION": "u8", "MODEL_DISTRIBUTION_POLICY": "PIPELINE_PARALLEL"}'
DRAFT_DEVICE="HETERO:GPU.0,GPU.1"
NUM_ASSISTANT_TOKENS=10
ASSISTANT_CONFIDENCE_THRESHOLD=0.5

BASE_PATH="$HOME/data/models/ov"
qwq_05b="$BASE_PATH/qwen/QwQwen-0.5B-int8_asym-ov"
qwen3_06b="$BASE_PATH/qwen/Qwen3-0.6B-int8_asym-ov/"
qwen3_6l06b="$BASE_PATH/qwen/Qwen3-pruned-6L-from-0.6B-int8-ov/"
qwen3_4b="$BASE_PATH/qwen/Qwen3-4B-Instruct-2507-int4_asym-awq-ov/"
qwen3_8b="$BASE_PATH/qwen/Qwen3-8B-int4-cw-ov/"
qwen3_14b="$BASE_PATH/qwen/Qwen3-14B-int4_sym-ov/"
qwen3c_30b="$BASE_PATH/qwen/Qwen3-30B-A3B-Instruct-2507-int4-ov"
nemotron_14b="$BASE_PATH/other/Nemotron-Cascade-14B-Thinking-int4_asym-se-ov/"
nousc_14b="$BASE_PATH/nous/NousCoder-14B-int4_sym-ov/"

MODEL_PATH=$qwen3_14b
DRAFT_MODEL_PATH=$qwen3_06b
MODEL_NAME="qwen3"

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

openarc add "${ARGS[@]}"
openarc unload $MODEL_NAME
openarc load $MODEL_NAME
