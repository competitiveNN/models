#!/usr/bin/env bash

export ZE_AFFINITY_MASK=0
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT=1
export PYTORCH_ALLOC_CONF="expandable_segments:True"
export ONEAPI_DEVICE_SELECTOR="level_zero:gpu"

vllm serve --config /config.yaml
