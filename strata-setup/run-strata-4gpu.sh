#!/usr/bin/env bash
# Run the Strata SYCL server for Qwen3.8-Flash-Next IQ3_XXS on 4x Intel Arc B580 (PP=4).
# Extends run-strata-2gpu.sh for four Battlemage render nodes (renderD128 through renderD131).

MODEL_DIR="${MODEL_DIR:-/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF}"
IMAGE="${IMAGE:-localhost/strata-old:latest}"
NAME="${NAME:-strata-4gpu}"
HOST_PORT="${HOST_PORT:-1235}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"

CTX="${CTX:-65536}"
PREFILL="${PREFILL:-49152}"
KV_RESIDENT="${KV_RESIDENT:-65536}"
VRAM_RESERVE="${VRAM_RESERVE:-32}"
EXPERT_CACHE="${EXPERT_CACHE:-32768}"
SPEC="${SPEC:-8}"
POOL_WORKERS="${POOL_WORKERS:-32}"
GPU="${GPU:-3,2,1,0}"

GPU_DEVICES=(
    --device=/dev/dri/renderD128
    --device=/dev/dri/renderD129
    --device=/dev/dri/renderD130
    --device=/dev/dri/renderD131
)

ROOT="$(cd "$(dirname "$0")" && pwd)"

LAUNCH_CMD="mkdir -p /root/.local/share/strata/components/engine && cp -r /opt/strata/components/engine/0.1.59-linux-x86_64-sycl /root/.local/share/strata/components/engine/ 2>/dev/null; /opt/strata/terminal/bin/strata launch \
    --no-api-key \
    --no-tui \
    --family swift \
    --model IQ3_XXS \
    --model-path /model/ \
    --data-dir /data/Strata-data \
    --context ${CTX} \
    --vision off \
    --access lan \
    --port 8080 \
    --gpu ${GPU} \
    --parallel 1 \
    --mtp on \
    --drafting auto \
    --set pipeline-windows=4 \
    --set vram-reserve-mib=${VRAM_RESERVE} \
    --set expert-cache=${EXPERT_CACHE} \
    --set spec=${SPEC} \
    --set trim-stage-weights \
    --set kv=int4 \
    --set prefill=auto:${PREFILL} \
    --set peer-prefill-rows=4 \
    --set spec-min-p=0.3 \
    --set pool-workers=${POOL_WORKERS} \
    --set pool-affinity=p-cores \
    --set host-core=first \
    --set expert-cache-per-layer \
    --set stream-experts \
    --set mmap-experts"
LAUNCH_CMD="${LAUNCH_CMD}; sleep infinity"

podman run -d \
    --privileged \
    --name="$NAME" \
    "${GPU_DEVICES[@]}" \
    --user=root \
    --publish="${HOST_PORT}:${CONTAINER_PORT}" \
    --ulimit=core=0 \
    --stop-timeout=120 \
    --volume="${MODEL_DIR}:/model/:Z,U" \
    --volume="${ROOT}/Strata-data:/data/Strata-data:Z,U" \
    --env=SYCL_CACHE_PERSISTENT=1 \
    --env='ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1;level_zero:2;level_zero:3' \
    --env=STRATA_SPIN_MAX=200000000 \
    --env=STRATA_PREFILL_RING=1024 \
    --env=STRATA_STAGER_RING=256 \
    --env=STRATA_MIRROR_MIB=32768 \
    --env=STRATA_VERIFY_DEVICE_PLAN=1 \
    --env=STRATA_STAGE_TRIM=1 \
    --env=STRATA_RING_TIMEOUT_S=600 \
    --env=STRATA_PREFILL_MMQ=1 \
    --env=STRATA_WINDOW_SYNC=0 \
    --env=IGC_EnableGEPSimplification=0 \
    --env=STRATA_COPY_ENGINE=0 \
    --env=STRATA_PCIE_SPLIT_MODE=distributed \
    --env=STRATA_MOE_DMA_OVERLAP=1 \
    --env=STRATA_ASYNC_RING_BUFFER=1 \
    --env=STRATA_DMA_BATCH=256 \
    --env=STRATA_FETCH_THREADS=32 \
    --env=STRATA_POOL_SPIN_US=100 \
    --rm \
    --entrypoint=/bin/bash \
    "$IMAGE" \
    -c "$LAUNCH_CMD"
