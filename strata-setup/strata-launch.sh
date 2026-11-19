#!/bin/bash
# strata-launch.sh - Launch a Strata SYCL inference server in a container.
#
# Usage: ./strata-launch.sh [OPTIONS] [PORT] [MODEL_NAME]
#   --image, -i IMG   container image: dev (default) | old | edge | <name>[:tag]
#   --1gpu            use the 1-GPU TDR-safe config (tdr-safe-1gpu-fixed)
#   --2gpu, --tp2     use the 2-GPU config (strata-swift-iq3_xxs-2gpu-clean)
#   --config PATH     host JSON config to mount in (editable; overrides in-image)
#   PORT              default: 8082 (1gpu) / 8081 (2gpu)
#   MODEL_NAME        default: tdr-safe-1gpu (1gpu) / strata-swift-iq3_xxs-2gpu-clean (2gpu)
#
# dev image bind-mounts the host repo (code from host); old/edge are self-contained
# (code comes from the image) and default to 2-GPU.

set -euo pipefail

IMAGE="${STRATA_SYCL_IMAGE:-strata-sycl-dev}"
CONFIG_HOST="${STRATA_CONFIG_HOST:-}"
GGUF_DIR="${GGUF_DIR:-}"
GPU_MODE=""   # "" = auto (2gpu for old/edge, 1gpu for dev)
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --image|-i) IMAGE="$2"; shift 2 ;;
    --image=*) IMAGE="${1#*=}"; shift ;;
    --1gpu) GPU_MODE="1"; shift ;;
    --2gpu|--tp2) GPU_MODE="2"; shift ;;
    --config) CONFIG_HOST="$2"; shift 2 ;;
    --config=*) CONFIG_HOST="${1#*=}"; shift ;;
    --gguf) GGUF_DIR="$2"; shift 2 ;;
    --gguf=*) GGUF_DIR="${1#*=}"; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

# image shortcuts
case "$IMAGE" in
  dev)  IMAGE="strata-sycl-dev:latest" ;;
  old)  IMAGE="strata-old:latest" ;;
  edge) IMAGE="strata-edge:latest" ;;
esac
case "$IMAGE" in *:*) ;; *) IMAGE="$IMAGE:latest" ;; esac

# auto GPU mode
if [ -z "$GPU_MODE" ]; then
  case "$IMAGE" in
    *strata-old*|*strata-edge*) GPU_MODE="2" ;;
    *) GPU_MODE="1" ;;
  esac
fi

# self-contained? (old/edge ship their own /work/strata-src)
SELF_CONTAINED=0
case "$IMAGE" in *strata-old*|*strata-edge*) SELF_CONTAINED=1 ;; esac

if [ "$GPU_MODE" = "2" ]; then
  DEFAULT_PORT=8081
  DEFAULT_MODEL="strata-swift-iq3_xxs-2gpu-clean"
  CONFIG_NAME="strata-swift-iq3_xxs-2gpu-clean.json"
else
  DEFAULT_PORT=8082
  DEFAULT_MODEL="tdr-safe-1gpu"
  CONFIG_NAME="tdr-safe-1gpu-fixed.json"
fi

PORT="${POSITIONAL[0]:-$DEFAULT_PORT}"
MODEL_NAME="${POSITIONAL[1]:-$DEFAULT_MODEL}"

CONTAINER_NAME="strata-${GPU_MODE}gpu"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$REPO_ROOT/runs"

# Colors
GREEN='\033[0;32m'; YELLOW='\033[1;32m'; RED='\033[0;31m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

command -v podman >/dev/null 2>&1 || { log_error "podman not found"; exit 1; }
if ! podman image exists "$IMAGE" 2>/dev/null; then
    log_error "Container image '$IMAGE' not found. Build it first:"; exit 1
fi

# Build podman args
RUN_ARGS=(run -d --privileged --name "$CONTAINER_NAME" --replace --network host
  --device /dev/dri --device /dev/dri/card0 --device /dev/dri/card1
  --device /dev/dri/renderD128 --device /dev/dri/renderD129)

# Resolve --config to an ABSOLUTE path once (podman treats a relative bind
# source as a named volume and fails with "names must match ...").
if [ -n "$CONFIG_HOST" ]; then
  if [ ! -f "$CONFIG_HOST" ] && [ -f "$REPO_ROOT/configs/$CONFIG_HOST" ]; then
    CONFIG_HOST="$REPO_ROOT/configs/$CONFIG_HOST"
  fi
  if [ ! -f "$CONFIG_HOST" ] && [ -f "$REPO_ROOT/configs/${CONFIG_HOST}.json" ]; then
    CONFIG_HOST="$REPO_ROOT/configs/${CONFIG_HOST}.json"
  fi
  [ -f "$CONFIG_HOST" ] || { log_error "config not found: $CONFIG_HOST"; exit 1; }
  CONFIG_HOST="$(cd "$(dirname "$CONFIG_HOST")" && pwd)/$(basename "$CONFIG_HOST")"
  CFG_BASE="$(basename "$CONFIG_HOST")"
  CONFIG_NAME="$CFG_BASE"
fi

if [ "$SELF_CONTAINED" = "1" ]; then
  RUN_ARGS+=(-v "$REPO_ROOT/Strata-data:/work/Strata-data:Z"
             -v "$REPO_ROOT/runs:/work/runs:Z")
  : "${GGUF_DIR:=/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF}"
  if [ -d "$GGUF_DIR" ]; then RUN_ARGS+=(-v "$GGUF_DIR:/gguf:ro"); fi
else
  RUN_ARGS+=(-v "$REPO_ROOT:/work:Z")
fi

# Mount the config into the place the server reads it from, in both image modes.
if [ -n "$CONFIG_HOST" ]; then
  RUN_ARGS+=(-v "$CONFIG_HOST:/work/strata-src/$CFG_BASE:Z")
fi

RUN_ARGS+=(-e "LD_LIBRARY_PATH=/opt/intel/oneapi/compiler/2026.2/lib:/opt/intel/oneapi/mkl/2026.2/lib:/opt/intel/oneapi/redist/lib:/opt/intel/oneapi/umf/1.2/lib")
[ "$GPU_MODE" = "2" ] && RUN_ARGS+=(-e "ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1")

# Stop existing
podman rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

log_info "Launching Strata ($IMAGE, ${GPU_MODE}GPU) on port $PORT..."
if ! podman "${RUN_ARGS[@]}" "$IMAGE" \
  -c "cd /work/strata-src && exec python3 sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CONFIG_NAME --port $PORT" \
  >/dev/null; then
  log_error "podman run failed (see the message above)"; exit 1
fi

# Wait for ready
MAX_WAIT=300
for i in $(seq 1 $MAX_WAIT); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"loaded": true'; then
    log_info "Server ready on http://127.0.0.1:$PORT"; exit 0; fi
  if ! podman ps --format '{{.Names}}' | grep -q "^$CONTAINER_NAME$"; then
    log_error "Container died during startup"; podman logs "$CONTAINER_NAME" 2>&1 | tail -15; exit 1; fi
  sleep 2
done
log_error "Server did not become ready"; podman logs "$CONTAINER_NAME" 2>&1 | tail -15; exit 1
