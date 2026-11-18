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
#   * the 256K context and `expert-cache=20000` do not fit twice over two B580s, so the
#     run dropped to --context 65536, expert-cache=0 (experts stream from RAM, which is
#     where the model spends its VRAM) and vram-reserve-mib=512;
#   * kv-resident=32768 keeps half the KV window on the cards and streams the rest;
#   * LAN access, port 8080/1235 and the SPIN_MAX / PREFILL_RING tuning are unchanged.
#
# Usage: ./run-strata-2gpu.sh
#   Tune the fit:  CTX=262144 PREFILL=8192 KV_RESIDENT=4096 VRAM_RESERVE=512 ./run-strata-2gpu.sh

MODEL_DIR="${MODEL_DIR:-/home/fra/dev/models/XeStrata-data/models/IQ3_XXS}"
IMAGE="${IMAGE:-ghcr.io/niko1221/strata:0.2.13-sycl}"
NAME="${NAME:-strata}"
HOST_PORT="${HOST_PORT:-1235}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"
# Context and prompt-chunk tuning.
#   * PREFILL is the prompt chunk (tokens).  Measured on 2x B580: 8192 is the sweet
#     spot (1677 tok/s prefill at 28.5k tokens vs 1514 at 4096); 16384 regresses.
#   * KV_RESIDENT keeps that many KV cells on the cards and streams the rest.  65536
#     (full residency) loads fine (430 MiB free) and gives ~27 tok/s decode at 55k
#     context vs ~22 tok/s at 32768.
CTX="${CTX:-262144}"
PREFILL="${PREFILL:-8192}"
KV_RESIDENT="${KV_RESIDENT:-4096}"
VRAM_RESERVE="${VRAM_RESERVE:-512}"

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
    -c 'strata launch \
        --drafting off \
        --mtp off \
        --set vram-reserve-mib='"${VRAM_RESERVE}"' \
        --no-api-key \
        --no-tui \
        --family qwen \
        --model IQ3_XXS \
        --model-path /model/ \
        --context '"${CTX}"' \
        --vision off \
        --access lan \
        --port 8080 \
        --gpu 0,1 \
        --set prefill='"${PREFILL}"' \
        --set prefill-borrow=on \
        --set spec=4 \
        --parallel 1 \
        --set expert-cache=0 \
        --set kv-resident='"${KV_RESIDENT}"' \
        --set pipeline-windows=2 \
        --set expert-cache-per-layer \
        --set trim-stage-weights; \
      sleep infinity'
