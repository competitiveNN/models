#!/usr/bin/env bash
# Run the Strata SYCL server for Qwen3.8-Flash-Next IQ3_XXS on 2x Intel Arc B580.
#
# Derived from the single-card podman command:
#   podman run ... --device=/dev/dri/renderD129 --volume=...IQ3_XXS/:/model/ ...
#     'strata launch --drafting off --mtp off ... --family swift --model IQ3_XXS ...'
#
# Changes for the two B580 cards (Battlemage G21, renderD128 + renderD129):
#   * both render nodes are passed to the container (the old command bound only renderD129);
#   * ONEAPI_DEVICE_SELECTOR names both Level-Zero devices instead of `level_zero:*`;
#   * `--gpu 0,1` makes strata split the layers over the two cards (apply_cards sets
#     layer_split=auto for a two-card list);
#   * `--set pipeline-windows=2` overlaps stage 0 / stage 1, the split's win at long
#     context (the engine only defaults it to 2 when the MTP drafter is on, and this run
#     keeps the drafter off);
#   * `--set expert-cache-per-layer` gives each layer its own VRAM slots, which matters
#     more on a split where each card holds a different set of layers;
#   * `--set trim-stage-weights` lets each card load only its own layers' dense weights,
#     leaving more VRAM for the expert cache;
#   * the model path points at the GGUF directory passed via MODEL_DIR (defaults to
#     the Swift-1.5 Qwen3.8 Flash-Next GSQ-RCO GGUF folder under ~/data/models/gguf/;
#     override with MODEL_DIR=... for a different folder).
#
# Differences from the single-card command that matter for 12 GB cards:
#   * the 64K context fits on two B580s with full KV residency; expert-cache=20000 is
#     a slot count, not a budget, so it runs at 0 (auto) instead;
#   * vram-reserve-mib=512 keeps room for the prompt staging;
#   * kv-resident=65536 keeps the whole 64K KV window on the cards (no streaming).
#
# Measured on 2x Arc B580 (12 GB each) at 64K context:
#   * prompt chunk 8192 is the sweet spot (+11% over 4096 on a 28.5k-token prompt);
#   * 16384 regressed, 30000 would need ~20 GiB of prompt buffer on one card;
#   * with PREFILL=8192 the run loads with ~430 MiB free and prefill ~970 tok/s,
#     decode ~27 tok/s.
# Usage: ./run-strata-2gpu.sh [--strata-defaults | --fast-prefill]
#   --strata-defaults: use verified winner config as baseline (SPEC=4, EXPERT_CACHE=8192, PEER_PREFILL_ROWS=4, POOL_WORKERS=20)
#   --fast-prefill: use fast prefill tuning adapted for 2x B580 and strata-old (CTX=262144, prefill=30000, prefill-borrow=on, expert-cache=20000, kv-resident=32768, vram-reserve-mib=0)
#   Tune the fit:  CTX=64k PREFILL=8192 KV_RESIDENT=65536 VRAM_RESERVE=256 CORES=8 ./run-strata-2gpu.sh
#   Decode parallelism:  PARALLEL=4 ./run-strata-2gpu.sh   (1..8 requests decoding together)
#   Pin to specific cores:  CORES=\"0,2,4,6\" ./run-strata-2gpu.sh   (or CORES=off to disable pinning)

# Parse mode flags
FAST_PREFILL="0"
USE_STRATA_DEFAULTS="0"
for arg in "$@"; do
  case "$arg" in
    --fast-prefill)
      FAST_PREFILL="1"
      shift
      ;;
    --strata-defaults)
      USE_STRATA_DEFAULTS="1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done
if [ "$FAST_PREFILL" != "1" ] && [ "$USE_STRATA_DEFAULTS" != "1" ]; then
    FAST_PREFILL="0"
    USE_STRATA_DEFAULTS="0"
fi

MODEL_DIR="${MODEL_DIR:-/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF}"
IMAGE="${IMAGE:-localhost/strata-old:latest}"
NAME="${NAME:-strata-ceiling}"
HOST_PORT="${HOST_PORT:-1236}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"

if [ "$FAST_PREFILL" = "1" ]; then
    CTX="${CTX:-131072}"
    PREFILL="${PREFILL:-16384}"
    PREFILL_BORROW="${PREFILL_BORROW:-on}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-65536}"
    VRAM_RESERVE="${VRAM_RESERVE:-256}"
    EXPERT_CACHE="${EXPERT_CACHE:-20000}"
    SPEC="${SPEC:-4}"
    POOL_WORKERS="${POOL_WORKERS:-20}"
elif [ "$USE_STRATA_DEFAULTS" = "1" ]; then
    CTX="${CTX:-65536}"
    PREFILL="${PREFILL:-8192}"
    PREFILL_BORROW="${PREFILL_BORROW:-off}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-65536}"
    VRAM_RESERVE="${VRAM_RESERVE:-256}"
    EXPERT_CACHE="${EXPERT_CACHE:-20000}"
    SPEC="${SPEC:-4}"
    POOL_WORKERS="${POOL_WORKERS:-20}"
    FAMILY="${FAMILY:-swift}"
else
    CTX="${CTX:-65536}"
    PREFILL="${PREFILL:-8192}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-65536}"
    VRAM_RESERVE="${VRAM_RESERVE:-256}"
    EXPERT_CACHE="${EXPERT_CACHE:-20000}"
    SPEC="${SPEC:-4}"
    POOL_WORKERS="${POOL_WORKERS:-20}"
    FAMILY="${FAMILY:-swift}"
fi

FAMILY="${FAMILY:-swift}"
# PARALLEL: how many requests decode together (1 = one at a time; 2..8 = batch slots).
PARALLEL="${PARALLEL:-1}"
PIPELINE_WINDOWS="${PIPELINE_WINDOWS:-2}"
EXPERT_CACHE_PER_LAYER="${EXPERT_CACHE_PER_LAYER:-on}"
GPU="${GPU:-1,0}"
DRAFTING="${DRAFTING:-auto}"
MTP="${MTP:-on}"
KV="${KV:-int8}"
# CORES: number of CPU workers to pin (P-cores first). Empty = all P-cores; 0/off = no pinning.
CORES="${CORES:-}"
if [ ! -d "$MODEL_DIR" ]; then
    echo "run-strata-2gpu.sh: model folder not found: $MODEL_DIR" >&2
    echo "  set MODEL_DIR to the folder that holds the GGUF shards." >&2
    exit 2
fi
if ! find "$MODEL_DIR" -maxdepth 1 -type f -iname '*.gguf' | grep -q .; then
    echo "run-strata-2gpu.sh: no .gguf files found in $MODEL_DIR" >&2
    echo "  the script will still start podman, but strata will fail inside the container." >&2
    echo "  download the GGUF shards into that folder first." >&2
fi

# Both Battlemage cards: renderD128 (04:00.0) and renderD129 (86:00.0).
if [ "$GPU" = "0" ]; then
    GPU_DEVICES=( --device=/dev/dri/renderD128 )
elif [ "$GPU" = "1" ]; then
    GPU_DEVICES=( --device=/dev/dri/renderD129 )
else
    GPU_DEVICES=(
        --device=/dev/dri/renderD128
        --device=/dev/dri/renderD129
    )
fi

# Host repo root (for Strata-data/packs/swift-iq3_xxs)
ROOT="$(cd "$(dirname "$0")" && pwd)"

# --- CPU worker pinning (P-cores first) ---
# Detect logical CPUs and split them into P-cores (high max frequency) and the rest,
# so the CPU expert workers can be pinned to the performance cores on hybrid parts
# (e.g. Intel Core Ultra: 8 P-cores at ~5.4 GHz, 12 E-cores at ~4.6 GHz).
_MAXF=0
for _c in /sys/devices/system/cpu/cpu[0-9]*; do
    _f=$(cat "$_c/cpufreq/scaling_max_freq" 2>/dev/null || echo 0)
    [ "$_f" -gt "$_MAXF" ] 2>/dev/null && _MAXF=$_f
done
_P_CORES=""
_E_CORES=""
for _c in /sys/devices/system/cpu/cpu[0-9]*; do
    _n=${_c##*cpu}
    _f=$(cat "$_c/cpufreq/scaling_max_freq" 2>/dev/null || echo 0)
    if [ "$_MAXF" -gt 0 ] && [ "$_f" -ge "$((_MAXF * 9 / 10))" ]; then
        _P_CORES="${_P_CORES:+$_P_CORES,}$_n"
    else
        _E_CORES="${_E_CORES:+$_E_CORES,}$_n"
    fi
done
# CORES=N pins that many workers (P-cores first, then E-cores). Empty (default) pins
# CORES: number of workers (or explicit comma list like "0,2").
# Empty = all P-cores; 0/off = no pinning.
CORES="${CORES:-}"
if [ "$CORES" = "off" ] || [ "$CORES" = "0" ]; then
    _POOL_LIST=""
elif echo "$CORES" | grep -q ','; then
    _POOL_LIST="$CORES"
elif [ -n "$CORES" ]; then
    _POOL_LIST=$(printf '%s\n%s\n' "$_P_CORES" "$_E_CORES" | tr ',' '\n' | grep -v '^$' | head -n "$CORES" | paste -sd, -)
else
    CORES=$(printf '%s' "$_P_CORES" | tr ',' '\n' | grep -c .)
    _POOL_LIST=$(printf '%s\n%s\n' "$_P_CORES" "$_E_CORES" | tr ',' '\n' | grep -v '^$' | head -n "$CORES" | paste -sd, -)
fi
if [ -n "$_POOL_LIST" ]; then
    POOL_CORES_ARG="--pool-cores ${_POOL_LIST}"
else
    POOL_CORES_ARG=""
fi
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
    --parallel ${PARALLEL} \
    ${POOL_CORES_ARG} \
    --mtp ${MTP} \
    --drafting ${DRAFTING} \
    --set pipeline-windows=${PIPELINE_WINDOWS} \
    --set vram-reserve-mib=${VRAM_RESERVE} \
    --set expert-cache=${EXPERT_CACHE} \
    --set spec=${SPEC} \
    --set trim-stage-weights \
    --set kv=${KV} \
    --set prefill=auto:${PREFILL} \
    $( [ "$PREFILL_BORROW" = "on" ] && echo "--set prefill-borrow" ) \
    --set peer-prefill-rows=${PEER_PREFILL_ROWS} \
    --set spec-min-p=0.5 \
    --set pool-workers=${POOL_WORKERS} \
    --set pool-affinity=p-cores \
    --set host-core=first \
    $( [ "$EXPERT_CACHE_PER_LAYER" = "on" ] && echo "--set expert-cache-per-layer" ) \
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
    --volume="/var/home/fra/dev/models/strata-setup/Strata-data:/data/Strata-data:Z,U" \
    --env=SYCL_CACHE_PERSISTENT=1 \
    --env='ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1' \
    --env=STRATA_SPIN_MAX=200000000 \
    --env=STRATA_PREFILL_RING=16 \
    --env=STRATA_VERIFY_DEVICE_PLAN=1 \
    --env=STRATA_STAGE_TRIM=1 \
    --env=STRATA_RING_TIMEOUT_S=600 \
    --env=STRATA_SPLIT_WAIT_MS=600000 \
    --env=STRATA_VERIFY_DRAIN_TIMEOUT_MS=120000 \
    --env=STRATA_PREFILL_MMQ=${STRATA_PREFILL_MMQ:-auto} \
    --env=STRATA_WINDOW_SYNC=0 \
    --env=IGC_EnableGEPSimplification=0 \
    --env=STRATA_MIRROR_MIB=16384 \
    --env=STRATA_VERIFY_NO_HOST=0 \
    --env=STRATA_COPY_ENGINE=0 \
    --env=STRATA_SPLIT_MISS_MS=108 \
    --rm \
    --entrypoint=/bin/bash \
    "$IMAGE" \
    -c "$LAUNCH_CMD"
