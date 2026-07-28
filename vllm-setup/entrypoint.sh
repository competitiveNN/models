#!/usr/bin/env bash

# Source Intel oneAPI environment (suppress output since setvars may be re-sourced by vllm subprocesses)
source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1

#export ZE_SHARED_FORCE_DEVICE_ALLOC=1
export ZE_AFFINITY_MASK=0,1
export ONEAPI_DEVICE_SELECTOR="level_zero:0,1"
export FI_PROVIDER=shm 

export VLLM_TARGET_DEVICE=xpu
export VLLM_XPU_ENABLE_XPU_GRAPH=1
#export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

#export VLLM_WORKER_MULTIPROC_METHOD=spawn
#export PYTORCH_ALLOC_CONF="expandable_segments:True"
#export VLLM_OFFLOAD_WEIGHTS_BEFORE_QUANT=1

export CCL_TOPO_FABRIC_VERTEX_CONNECTION_CHECK=0
export CCL_ATL_TRANSPORT=ofi
export CCL_ATL_SHM=1
export FI_OFI_RXM_USE_SHM=1

#export OMP_NUM_THREADS=1
#export MKL_NUM_THREADS=1

#export VLLM_PP_LAYER_PARTITION="14,18" # must be set per model
#export VLLM_LOGGING_LEVEL=DEBUG
#export TORCH_DISTRIBUTED_DEBUG=DETAIL
#export NCCL_DEBUG=INFO

exec vllm serve --config /config.yaml
