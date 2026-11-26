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
# Measured on 2x Arc B580 (12 GB each, x8/x4 PCIe) at 64K context:
#   * prompt chunk 8192 is the sweet spot (+11% over 4096 on a 28.5k-token prompt);
#   * 16384 regressed, 30000 would need ~20 GiB of prompt buffer on one card;
#   * asymmetric PCIe limits prefill ~1060 tok/s, decode ~18.6 tok/s (bandwidth ceiling).
# Usage: ./run-strata-2gpu.sh [--strata-defaults | --fast-prefill | --kernel-fused-max]
#   --strata-defaults: verified winner baseline (SPEC=4, EXPERT_CACHE=8192, PEER_PREFILL_ROWS=4, POOL_WORKERS=20)
#   --fast-prefill: large-context prefill tuning (CTX=262144, prefill=30000, prefill-borrow=on, expert-cache=20000, kv-resident=32768, vram-reserve-mib=0)
#   --kernel-fused-max: evidence-backed async ring/DMA staging profile (CTX=65536, prefill=49152, spec=8, kv=int4, expert-cache=24576,
#     STRATA_PREFILL_RING=256, STRATA_STAGER_RING=64, STRATA_MIRROR_MIB=8192, STRATA_DMA_BATCH=64, STRATA_FETCH_THREADS=32,
#     STRATA_POOL_SPIN_US=100, STRATA_PCIE_SPLIT_MODE=asymmetric, STRATA_MOE_DMA_OVERLAP=1, STRATA_ASYNC_RING_BUFFER=1).
#     Source: configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json, runs/kernel-pipeline-verification.md.
#   Tune the fit:  CTX=64k PREFILL=8192 KV_RESIDENT=65536 VRAM_RESERVE=256 CORES=8 ./run-strata-2gpu.sh
#   Decode parallelism:  PARALLEL=4 ./run-strata-2gpu.sh   (1..8 requests decoding together)
#   Pin to specific cores:  CORES=\"0,2,4,6\" ./run-strata-2gpu.sh   (or CORES=off to disable pinning)

# Parse mode flags
FAST_PREFILL="0"
USE_STRATA_DEFAULTS="0"
KERNEL_FUSED_MAX="0"
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
    --kernel-fused-max)
      KERNEL_FUSED_MAX="1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done
if [ "$FAST_PREFILL" != "1" ] && [ "$USE_STRATA_DEFAULTS" != "1" ] && [ "$KERNEL_FUSED_MAX" != "1" ]; then
    FAST_PREFILL="0"
    USE_STRATA_DEFAULTS="0"
    KERNEL_FUSED_MAX="0"
fi

MODEL_DIR="${MODEL_DIR:-/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF}"
IMAGE="${IMAGE:-localhost/strata-old:latest}"
NAME="${NAME:-strata}"
HOST_PORT="${HOST_PORT:-1235}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"

if [ "$USE_STRATA_DEFAULTS" = "1" ]; then
    CTX="${CTX:-65536}"
    PREFILL="${PREFILL:-8192}"
    PREFILL_BORROW="${PREFILL_BORROW:-off}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-65536}"
    VRAM_RESERVE="${VRAM_RESERVE:-256}"
    EXPERT_CACHE="${EXPERT_CACHE:-8192}"
    SPEC="${SPEC:-4}"
    POOL_WORKERS="${POOL_WORKERS:-20}"
    FAMILY="${FAMILY:-swift}"
    # OOM-safe baseline overrides for 2x B580 (12 GB each):
    STRATA_KV_HOST_DMA="${STRATA_KV_HOST_DMA:-1}"
    STRATA_ADAPT_OVERLAP="${STRATA_ADAPT_OVERLAP:-1}"
    STRATA_GR_FUSED="${STRATA_GR_FUSED:-1}"
    STRATA_PREFILL_RING="${STRATA_PREFILL_RING:-128}"
    STRATA_STAGER_RING="${STRATA_STAGER_RING:-32}"
    STRATA_MIRROR_MIB="${STRATA_MIRROR_MIB:-4096}"
    STRATA_DMA_BATCH="${STRATA_DMA_BATCH:-32}"
    STRATA_QSA_ROWS="${STRATA_QSA_ROWS:-1}"
elif [ "$FAST_PREFILL" = "1" ]; then
    CTX="${CTX:-262144}"
    PREFILL="${PREFILL:-16384}"
    PREFILL_BORROW="${PREFILL_BORROW:-on}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-32768}"
    VRAM_RESERVE="${VRAM_RESERVE:-128}"
    EXPERT_CACHE="${EXPERT_CACHE:-12000}"
    SPEC="${SPEC:-4}"
    POOL_WORKERS="${POOL_WORKERS:-20}"
    FAMILY="${FAMILY:-swift}"
    # OOM-safe fast-prefill overrides for 2x B580 (12 GB each):
    STRATA_KV_HOST_DMA="${STRATA_KV_HOST_DMA:-1}"
    STRATA_ADAPT_OVERLAP="${STRATA_ADAPT_OVERLAP:-1}"
    STRATA_GR_FUSED="${STRATA_GR_FUSED:-1}"
    STRATA_PREFILL_RING="${STRATA_PREFILL_RING:-256}"
    STRATA_STAGER_RING="${STRATA_STAGER_RING:-64}"
    STRATA_MIRROR_MIB="${STRATA_MIRROR_MIB:-8192}"
    STRATA_DMA_BATCH="${STRATA_DMA_BATCH:-64}"
    STRATA_QSA_ROWS="${STRATA_QSA_ROWS:-1}"
elif [ "$KERNEL_FUSED_MAX" = "1" ]; then
    # Evidence-backed aggressive async ring/DMA staging profile (adjusted for OOM safety on 12GB B580).
    # Source: configs/strata-swift-iq3_xxs-2gpu-kernel-fused-max.json,
    # runs/kernel-pipeline-verification.md.
    # 262K context support: KV=int4 (q4_0), partial KV residency, reduced expert cache.
    CTX="${CTX:-262144}"
    PREFILL="${PREFILL:-16384}"
    PREFILL_BORROW="${PREFILL_BORROW:-on}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-65536}"
    VRAM_RESERVE="${VRAM_RESERVE:-256}"
    EXPERT_CACHE="${EXPERT_CACHE:-8000}"
    SPEC="${SPEC:-8}"
    POOL_WORKERS="${POOL_WORKERS:-32}"
    FAMILY="${FAMILY:-swift}"
    KV="${KV:-q4_0}"
    PREFILL_MMQ="${PREFILL_MMQ:-1}"
    STRATA_PREFILL_RING="${STRATA_PREFILL_RING:-256}"
    STRATA_STAGER_RING="${STRATA_STAGER_RING:-64}"
    STRATA_MIRROR_MIB="${STRATA_MIRROR_MIB:-8192}"
    STRATA_DMA_BATCH="${STRATA_DMA_BATCH:-64}"
    STRATA_FETCH_THREADS="${STRATA_FETCH_THREADS:-32}"
    STRATA_POOL_SPIN_US="${STRATA_POOL_SPIN_US:-100}"
    STRATA_PCIE_SPLIT_MODE="${STRATA_PCIE_SPLIT_MODE:-asymmetric}"
    STRATA_MOE_DMA_OVERLAP="${STRATA_MOE_DMA_OVERLAP:-1}"
    STRATA_ASYNC_RING_BUFFER="${STRATA_ASYNC_RING_BUFFER:-1}"
    SPEC_MIN_P="${SPEC_MIN_P:-0.3}"
    STRATA_KV_HOST_DMA="${STRATA_KV_HOST_DMA:-1}"
    STRATA_ADAPT_OVERLAP="${STRATA_ADAPT_OVERLAP:-1}"
    STRATA_GR_FUSED="${STRATA_GR_FUSED:-1}"
    STRATA_QSA_ROWS="${STRATA_QSA_ROWS:-1}"
else
    CTX="${CTX:-65536}"
    PREFILL="${PREFILL:-8192}"
    PREFILL_BORROW="${PREFILL_BORROW:-off}"
    PEER_PREFILL_ROWS="${PEER_PREFILL_ROWS:-4}"
    KV_RESIDENT="${KV_RESIDENT:-65536}"
    VRAM_RESERVE="${VRAM_RESERVE:-256}"
    EXPERT_CACHE="${EXPERT_CACHE:-8192}"
    SPEC="${SPEC:-4}"
    POOL_WORKERS="${POOL_WORKERS:-20}"
    FAMILY="${FAMILY:-swift}"
fi
# Allow k/K suffixes (e.g. 4k, 16k, 64k, 128k, 256k) for convenience.
case "$CTX" in
  *[kK])
    _ctx_n="${CTX%[kK]}"
    if ! [[ "$_ctx_n" =~ ^[0-9]+$ ]]; then
      echo "run-strata-2gpu.sh: bad CTX value '$CTX' (expected a number or Nk)" >&2
      exit 2
    fi
    CTX=$(( _ctx_n * 1024 ))
    ;;
  *)
    if ! [[ "$CTX" =~ ^[0-9]+$ ]]; then
      echo "run-strata-2gpu.sh: bad CTX value '$CTX' (expected a number or Nk)" >&2
      exit 2
    fi
    ;;
esac

# Context size scaling logic for expert cache & KV residency:
# Automatically scale EXPERT_CACHE and KV_RESIDENT based on CTX to maximize VRAM usage without OOMing (24 GB total across 2x B580).
# - 64k+ ctx: EXPERT_CACHE=8192 (or 16384 for kernel-fused-max), KV_RESIDENT=65536
# - 32k ctx: EXPERT_CACHE=12288, KV_RESIDENT=32768
# - 16k ctx: EXPERT_CACHE=16384, KV_RESIDENT=16384
# - <=8k ctx: EXPERT_CACHE=20000, KV_RESIDENT=8192
if [ -z "${EXPERT_CACHE_SCALED:-}" ] && [ "${EXPERT_CACHE:-auto}" = "auto" ] || [ "${EXPERT_CACHE:-}" = "" ]; then
    if [ "$CTX" -ge 65536 ]; then
        EXPERT_CACHE="8192"
        KV_RESIDENT="${KV_RESIDENT:-65536}"
    elif [ "$CTX" -ge 32768 ]; then
        EXPERT_CACHE="12288"
        KV_RESIDENT="${KV_RESIDENT:-32768}"
    elif [ "$CTX" -ge 16384 ]; then
        EXPERT_CACHE="16384"
        KV_RESIDENT="${KV_RESIDENT:-16384}"
    else
        EXPERT_CACHE="20000"
        KV_RESIDENT="${KV_RESIDENT:-8192}"
    fi
fi
PARALLEL="${PARALLEL:-1}"
PIPELINE_WINDOWS="${PIPELINE_WINDOWS:-2}"
EXPERT_CACHE_PER_LAYER="${EXPERT_CACHE_PER_LAYER:-on}"
GPU="${GPU:-1,0}"
DRAFTING="${DRAFTING:-auto}"
MTP="${MTP:-on}"
KV="${KV:-int8}"
SPEC_MIN_P="${SPEC_MIN_P:-0.5}"
PREFILL_MMQ="${PREFILL_MMQ:-auto}"
# Async ring/DMA staging knobs (env-tunable; profile modes may set defaults above).
STRATA_PREFILL_RING="${STRATA_PREFILL_RING:-96}"
STRATA_STAGER_RING="${STRATA_STAGER_RING:-16}"
STRATA_MIRROR_MIB="${STRATA_MIRROR_MIB:-16384}"
STRATA_DMA_BATCH="${STRATA_DMA_BATCH:-64}"
STRATA_FETCH_THREADS="${STRATA_FETCH_THREADS:-16}"
STRATA_POOL_SPIN_US="${STRATA_POOL_SPIN_US:-1000}"
STRATA_PCIE_SPLIT_MODE="${STRATA_PCIE_SPLIT_MODE:-}"
STRATA_MOE_DMA_OVERLAP="${STRATA_MOE_DMA_OVERLAP:-}"
STRATA_ASYNC_RING_BUFFER="${STRATA_ASYNC_RING_BUFFER:-}"
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
    --set spec-min-p=${SPEC_MIN_P} \
    --set pool-workers=${POOL_WORKERS} \
    --set pool-affinity=p-cores \
    --set host-core=first \
    $( [ "$EXPERT_CACHE_PER_LAYER" = "on" ] && echo "--set expert-cache-per-layer" ) \
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
    --env='ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1' \
    --env=STRATA_SPIN_MAX=200000000 \
    --env=STRATA_PREFILL_RING=${STRATA_PREFILL_RING} \
    --env=STRATA_PREFILL_STREAM_ALL=${STRATA_PREFILL_STREAM_ALL:-1} \
    --env=STRATA_PREFILL_STREAM_MIN=${STRATA_PREFILL_STREAM_MIN:-1024} \
    --env=STRATA_STAGER_RING=${STRATA_STAGER_RING} \
    --env=STRATA_VERIFY_DEVICE_PLAN=1 \
    --env=STRATA_STAGE_TRIM=1 \
    --env=STRATA_RING_TIMEOUT_S=600 \
    --env=STRATA_PREFILL_MMQ=${PREFILL_MMQ} \
    --env=STRATA_WINDOW_SYNC=0 \
    --env=IGC_EnableGEPSimplification=0 \
    --env=STRATA_MIRROR_MIB=${STRATA_MIRROR_MIB} \
    --env=STRATA_VERIFY_NO_HOST=${STRATA_VERIFY_NO_HOST:-0} \
    --env=STRATA_COPY_ENGINE=${STRATA_COPY_ENGINE:-0} \
    --env=STRATA_SPLIT_MISS_MS=${STRATA_SPLIT_MISS_MS:-108} \
    --env=STRATA_ADAPT_LAG=${STRATA_ADAPT_LAG:-2} \
    --env=STRATA_ADAPT_OVERLAP=${STRATA_ADAPT_OVERLAP} \
    --env=STRATA_KV_HOST_DMA=${STRATA_KV_HOST_DMA} \
    --env=STRATA_GR_FUSED=${STRATA_GR_FUSED} \
    --env=STRATA_MTP_STAGE0=${STRATA_MTP_STAGE0:-1} \
    --env=STRATA_MTP_CATCHUP_ALL=${STRATA_MTP_CATCHUP_ALL:-1} \
    --env=STRATA_MTP_BATCH=${STRATA_MTP_BATCH:-1} \
    --env=STRATA_MTP_PRIORITY=${STRATA_MTP_PRIORITY:-1} \
    --env=STRATA_MTP_BATCH_RING=${STRATA_MTP_BATCH_RING:-1} \
    --env=STRATA_MTP_PREFILL_SYNC=${STRATA_MTP_PREFILL_SYNC:-1} \
    --env=STRATA_LOOKAHEAD=${STRATA_LOOKAHEAD:-4} \
    --env=STRATA_FILL_AHEAD=${STRATA_FILL_AHEAD:-2} \
    --env=STRATA_DMA_BATCH=${STRATA_DMA_BATCH} \
    --env=STRATA_FETCH_THREADS=${STRATA_FETCH_THREADS} \
    --env=STRATA_LEND_MIRROR=${STRATA_LEND_MIRROR:-1} \
    --env=STRATA_EXCHANGE_ROTATE=${STRATA_EXCHANGE_ROTATE:-1} \
    --env=STRATA_PREFILL_HELP=${STRATA_PREFILL_HELP:-1} \
    --env=STRATA_PREFILL_HELP_FRAC=${STRATA_PREFILL_HELP_FRAC:-0.3} \
    --env=STRATA_PREFILL_LEND_PCT=${STRATA_PREFILL_LEND_PCT:-50} \
    --env=STRATA_PF_DMA_PAGEABLE=${STRATA_PF_DMA_PAGEABLE:-1} \
    --env=STRATA_CHUNKED_FILL=${STRATA_CHUNKED_FILL:-1} \
    --env=STRATA_KV_PREFETCH=${STRATA_KV_PREFETCH:-1} \
    --env=STRATA_QSA_ROWS=${STRATA_QSA_ROWS} \
    --env=STRATA_DISJOINT_ADAPT=${STRATA_DISJOINT_ADAPT:-1} \
    --env=STRATA_PIPELINE_PRESTAGE=${STRATA_PIPELINE_PRESTAGE:-1} \
    --env=STRATA_POOL_SPIN_US=${STRATA_POOL_SPIN_US} \
    --env=STRATA_IQ_PREFETCH=${STRATA_IQ_PREFETCH:-1} \
    --env=STRATA_KV_STAGE_OWN=${STRATA_KV_STAGE_OWN:-1} \
    --env=STRATA_RING_BYTES=${STRATA_RING_BYTES:-1} \
    $( [ -n "$STRATA_PCIE_SPLIT_MODE" ] && echo "--env=STRATA_PCIE_SPLIT_MODE=${STRATA_PCIE_SPLIT_MODE}" ) \
    $( [ -n "$STRATA_MOE_DMA_OVERLAP" ] && echo "--env=STRATA_MOE_DMA_OVERLAP=${STRATA_MOE_DMA_OVERLAP}" ) \
    $( [ -n "$STRATA_ASYNC_RING_BUFFER" ] && echo "--env=STRATA_ASYNC_RING_BUFFER=${STRATA_ASYNC_RING_BUFFER}" ) \
    --env=STRATA_VERIFY_ALL_RESIDENT=${STRATA_VERIFY_ALL_RESIDENT:-0} \
    --rm \
    --entrypoint=/bin/bash \
    "$IMAGE" \
    -c "$LAUNCH_CMD"

# (The advanced async, extreme, and ultra-aggressive tuning flags are passed to the container via
# the --env= lines above in the podman run command.)
# Placeholder SYCL flags for future fork optimizations (not currently wired):
#   --env=STRATA_KVA=0 \
#   --env=STRATA_GDN_TC=0 \
#   --env=STRATA_PREFILL_LAYER_MAJOR=0 \
#   --env=STRATA_PREFILL_FUSED=1 \
#   --env=STRATA_LEND_MIRROR=1 \
#   --env=STRATA_EXCHANGE_ROTATE=1 \
