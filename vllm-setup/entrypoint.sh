#!/usr/bin/env bash

exec bash
export ZE_AFFINITY_MASK=0
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT=1
export PYTORCH_ALLOC_CONF="expandable_segments:True"

vllm serve \
	--model /home/fra/data/models/MLX-Qwen3.5-9B-Claude-4.6-Opus-Reasoning-Distilled-v2-4bit \
	--served-model-name Qwen3.5-9B \
	--port 8009 \
	--host 0.0.0.0 \
	--tensor-parallel-size 1 \
	--quantization fp8 \
	--gpu-memory-util 0.9 \
	--max-num-batched-tokens 8192 \
	--max-model-len 8192 \
	--block-size 64 \
	--dtype float16 \
	--enforce-eager \
	--trust-remote-code \
	--disable-log-requests
