#!/usr/bin/env bash
# serve-qwen-flash-next.sh — Optimized llama-server launcher for Qwen3.8 Flash Next (MoE)
#
# Uses llamacpp.py (Docker launcher) with optimized flags.
#
# Usage:
#   ./serve-qwen-flash-next.sh [options] [-- <extra llama.cpp args>]
#
# Options:
#   --port PORT        Server port (default: 8080)
#   --ctx SIZE         Context size in tokens or with k/m suffix (default: 128k)
#   --threads N        CPU threads (default: 8)
#   --no-mlock         Disable mlock (default: enabled)
#   --no-cb            Disable continuous batching (default: enabled)
#   --no-cache         Disable prompt caching (default: enabled)
#   --no-flash-attn    Disable Flash Attention (default: enabled)
#   --cpu-moe          Keep all MoE experts on CPU (default)
#   --n-cpu-moe N      Keep first N layers' MoE experts on CPU
#   --moe-cache-mib N  GPU cache size in MiB for MoE experts kept in CPU (PR #29887)
#   --help             Show this help

set -euo pipefail

# Default configuration — optimized for 2x Intel Arc B580 (24GB VRAM) + Core i5-265KF + 64GB DDR5
PORT=8080
CTX_SIZE="128k"
THREADS=8
MLOCK=1
CONT_BATCHING=1
CACHE_PROMPT=1
FLASH_ATTN=1
MOE_FLAG="--n-cpu-moe 8"   # Keep first 8 layers' experts on CPU (experts cache)
MOE_CACHE_MIB=0             # MoE cache disabled for multi-GPU (doesn't support multiple devices)
NGPU_LAYERS="all"           # Offload all layers to GPU (2x B580, 24GB VRAM)
EXTRA_ARGS=()

# Parse context size with k/m suffixes
parse_ctx_size() {
    local value="$1"
    if [[ "$value" =~ ^([0-9]+)([km]?)$ ]]; then
        local num="${BASH_REMATCH[1]}"
        local suffix="${BASH_REMATCH[2]}"
        case "$suffix" in
            k|K) echo $((num * 1024)) ;;
            m|M) echo $((num * 1024 * 1024)) ;;
            *) echo "$num" ;;
        esac
    else
        echo "$value"
    fi
}

# Usage
usage() {
    echo "Usage: $0 [options] [-- <extra llama.cpp args>]"
    echo "  --port PORT        Server port (default: 8080)"
    echo "  --ctx SIZE         Context size in tokens or with k/m suffix (default: 128k)"
    echo "  --threads N        CPU threads (default: 8)"
    echo "  --ngl N            GPU layers (default: all, for 2x B580)"
    echo "  --no-mlock         Disable mlock (default: enabled)"
    echo "  --no-cb            Disable continuous batching (default: enabled)"
    echo "  --no-cache         Disable prompt caching (default: enabled)"
    echo "  --no-flash-attn    Disable Flash Attention (default: enabled)"
    echo "  --cpu-moe          Keep all MoE experts on CPU (experts cache)"
    echo "  --n-cpu-moe N      Keep first N layers' MoE experts on CPU (default: 8)"
    echo "  --moe-cache-mib N  GPU cache size in MiB for MoE experts kept in CPU (default: 4096)"
    echo "  --help             Show this help"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --ctx) CTX_SIZE="$2"; shift 2 ;;
        --threads) THREADS="$2"; shift 2 ;;
        --no-mlock) MLOCK=0; shift ;;
        --no-cb) CONT_BATCHING=0; shift ;;
        --no-cache) CACHE_PROMPT=0; shift ;;
        --no-flash-attn) FLASH_ATTN=0; shift ;;
        --cpu-moe) MOE_FLAG="--cpu-moe"; shift ;;
        --n-cpu-moe) MOE_FLAG="--n-cpu-moe $2"; shift 2 ;;
        --moe-cache-mib) MOE_CACHE_MIB="$2"; shift 2 ;;
        --ngl) NGPU_LAYERS="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        --) shift; EXTRA_ARGS=("$@"); break ;;
        *) EXTRA_ARGS+=("$1"); shift ;;
    esac
done

# Resolve context size
CTX_SIZE_VAL=$(parse_ctx_size "$CTX_SIZE")

# Build llamacpp.py command
LLAMACPP="/var/home/fra/dev/models/llama.cpp-setup/llamacpp.py"
LLAMA_ARGS=(
    server
    --ctx-size "$CTX_SIZE_VAL"
    -ctk q5_1
    -ctv q4_0
    --n-gpu-layers "$NGPU_LAYERS"
    --threads "$THREADS"
    --port "$PORT"
    --timeout 3600
    -a qwen3.8-flash-next
    -lv 3
)

# MoE experts cache optimization
if [[ "$MOE_FLAG" == "--cpu-moe" ]]; then
    LLAMA_ARGS+=(--cpu-moe)
else
    LLAMA_ARGS+=(--n-cpu-moe "${MOE_FLAG#--n-cpu-moe }")
fi

# MoE experts GPU cache (PR #29887)
if [[ $MOE_CACHE_MIB -gt 0 ]]; then
    LLAMA_ARGS+=(--moe-cache-mib "$MOE_CACHE_MIB")
fi

# Flash Attention
if [[ $FLASH_ATTN -eq 1 ]]; then
    LLAMA_ARGS+=(--flash-attn on)
else
    LLAMA_ARGS+=(--flash-attn off)
fi

# Memory lock — requires --cap-add=IPC_LOCK in Docker; disabled by default in container
# To enable: add --cap-add=IPC_LOCK to docker run or use --mlock directly on host
if [[ $MLOCK -eq 1 ]]; then
    LLAMA_ARGS+=(--mlock)
fi

# Continuous batching
if [[ $CONT_BATCHING -eq 1 ]]; then
    LLAMA_ARGS+=(--cont-batching)
fi

# Prompt caching
if [[ $CACHE_PROMPT -eq 1 ]]; then
    LLAMA_ARGS+=(--cache-prompt)
fi

# Extra args
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    LLAMA_ARGS+=("${EXTRA_ARGS[@]}")
fi

# Print command
echo "llama-server command:"
printf " %q" "${LLAMA_ARGS[@]}"
echo
echo ""

# Execute via llamacpp.py (Docker launcher)
exec python3 "$LLAMACPP" "${LLAMA_ARGS[@]}"
