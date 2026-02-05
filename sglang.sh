#!/bin/bash

source ~/dev/sglang-setup/.venv/bin/activate
#MODEL="$HOME/data/models/safetensors/Qwen3-30B-A3B-GPTQ-Int4"
#MODEL="$HOME/data/models/safetensors/GLM-4.7-Flash-int4-AutoRound"
#MODEL="$HOME/data/models/safetensors/GLM-4.7-Flash-AWQ-4bit"
#MODEL="$HOME/data/models/safetensors/Qwen3-VL-8B-Instruct-unsloth-bnb-4bit"
#MODEL="$HOME/data/models/safetensors/DeepSeek-OCR"
#MODEL="$HOME/data/models/safetensors/DeepSeek-OCR-2"
MODEL="$HOME/data/models/safetensors/Qwen3-VL-32B-Instruct-AWQ-4bit"

python -m sglang.launch_server \
    --model "$MODEL" \
    --trust-remote-code \
    --disable-overlap-schedule \
    --device xpu \
    --host 0.0.0.0 \
    --tp 2 \
    --attention-backend intel_xpu \
    --page-size 128 \
    --quantization compressed-tensors

