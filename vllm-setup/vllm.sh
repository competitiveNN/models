#!/bin/bash

# vLLM startup script for Intel XPU (fallback from Docker)
# This script runs vLLM directly from the .venv virtual environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Set environment variables for Intel XPU
export VLLM_TARGET_DEVICE=xpu
export ONEAPI_DEVICE_SELECTOR="level_zero:gpu"
export ZE_AFFINITY_MASK=0

# vLLM configuration
CONFIG="$SCRIPT_DIR/vllm.yaml"

# Run vLLM server
exec vllm serve --config "$CONFIG"
