#!/usr/bin/env bash

# Source Intel oneAPI environment (suppress output since setvars may be re-sourced by vllm subprocesses)
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1

export ZE_AFFINITY_MASK=0
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT=1
export PYTORCH_ALLOC_CONF="expandable_segments:True"
export ONEAPI_DEVICE_SELECTOR="level_zero:gpu"
export VLLM_TARGET_DEVICE=xpu

exec vllm serve --config /config.yaml
