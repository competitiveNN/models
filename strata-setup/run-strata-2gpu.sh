#!/usr/bin/env bash
# Run the Strata SYCL server for Qwen3.8-Flash-Next IQ3_XXS on 2x Intel Arc B580.
#
# Derived from the single-card podman command:
#   podman run ... --device=/dev/dri/renderD129 --volume=...IQ3_XXS/:/model/ ...
#     'strata launch --drafting off --mtp off ... --family qwen --model IQ3_XXS ...'
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
#   * the 256K context needs a full two-card layer split, so the run uses both
#     render nodes (renderD128 + renderD129), `--gpu 0,1` and pipeline-windows=2;
#   * `expert-cache=20000` is a slot count, not a budget - on 12 GB cards the engine
#     auto-sizes from the leftover, so it runs at 0 (auto) instead;
#   * vram-reserve-mib=512 keeps room for the prompt staging;
#   * kv-resident=4096 keeps a small window on the cards and streams the rest of the
#     256K KV from RAM.
#
# Measured on 2x Arc B580 (12 GB each) at 256K context:
#   * prompt chunk 8192 is the sweet spot (+11% over 4096 on a 28.5k-token prompt);
#   * 16384 regressed, 30000 would need ~20 GiB of prompt buffer on one card;
#   * with PREFILL=8192 the run loads with ~450 MiB free and prefill ~1580 tok/s.
# Usage: ./run-strata-2gpu.sh
#   Tune the fit:  CTX=262144 PREFILL=8192 KV_RESIDENT=4096 VRAM_RESERVE=512 CORES=8 ./run-strata-2gpu.sh
#   Pin to specific cores:  CORES=\"0,2,4,6\" ./run-strata-2gpu.sh   (or CORES=off to disable pinning)
MODEL_DIR="${MODEL_DIR:-/home/fra/dev/models/XeStrata-data/models/IQ3_XXS}"
IMAGE="${IMAGE:-ghcr.io/niko1221/strata:0.2.13-sycl}"
NAME="${NAME:-strata}"
HOST_PORT="${HOST_PORT:-1235}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"
# Context and prompt-chunk tuning.
#   * CTX is the context window (256K).
#   * PREFILL is the prompt chunk (tokens): 8192 measured as the sweet spot.
#   * KV_RESIDENT keeps that many KV cells on the cards and streams the rest;
#     4096 loaded at 256K with ~450 MiB free.
CTX="${CTX:-262144}"
PREFILL="${PREFILL:-8192}"
KV_RESIDENT="${KV_RESIDENT:-4096}"
VRAM_RESERVE="${VRAM_RESERVE:-512}"
VRAM_RESERVE="${VRAM_RESERVE:-512}"
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
GPU_DEVICES=(
    --device=/dev/dri/renderD128
    --device=/dev/dri/renderD129
)

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
LAUNCH_CMD="strata launch \
    --drafting off \
    --mtp off \
    --set vram-reserve-mib=${VRAM_RESERVE} \
    --no-api-key \
    --no-tui \
    --family qwen \
    --model IQ3_XXS \
    --model-path /model/ \
    --context ${CTX} \
    --vision off \
    --access lan \
    --port 8080 \
    --gpu 0,1 \
    --set prefill=${PREFILL} \
    --set prefill-borrow=on \
    --set spec=4 \
    --parallel 1 \
    --set expert-cache=0 \
    --set kv-resident=${KV_RESIDENT} \
    --set pipeline-windows=2 \
    --set expert-cache-per-layer \
    --set trim-stage-weights"
if [ -n "$_POOL_LIST" ]; then
    LAUNCH_CMD="${LAUNCH_CMD} --pool-cores ${_POOL_LIST}"
fi
LAUNCH_CMD="${LAUNCH_CMD}; sleep infinity"

exec podman run --interactive --tty \
    --name="$NAME" \
    "${GPU_DEVICES[@]}" \
    --user=root \
    --publish="${HOST_PORT}:${CONTAINER_PORT}" \
    --ulimit=core=0 \
    --stop-timeout=120 \
    --volume="${MODEL_DIR}:/model/:Z,U" \
    --volume="${ROOT}/Strata-data:/data/Strata-data:Z,U" \
    --env=SYCL_CACHE_PERSISTENT=0 \
    --env='ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1' \
    --env=STRATA_SPIN_MAX=200000000 \
    --env=STRATA_PREFILL_RING=16 \
    --rm \
    --entrypoint=/bin/bash \
    "$IMAGE" \
    -c "$LAUNCH_CMD"
