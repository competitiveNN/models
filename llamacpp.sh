#!/bin/bash

MODELS_PATH="$HOME/data/models/gguf"
#MODEL="/models/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/Qwen3-30B-A3B-Instruct-2507-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Qwen3-4B-Instruct-2507-GGUF/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Magistral-Small-2509-GGUF-UD-Q4_K_XL/Magistral-Small-2509-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Magistral-Small-2509-GGUF-UD-Q4_K_XL/Magistral-Small-2509-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF-UD-Q4_K_XL/Mistral-Small-3.2-24B-Instruct-2506-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Devstral-Small-2-24B-Instruct-2512-GGUF-UD-Q4_K_XL/Devstral-Small-2-24B-Instruct-2512-UD-Q4_K_XL.gguf"
#MODEL="/models/unsloth/Magistral-Small-2509-GGUF-UD-Q4_K_XL/Magistral-Small-2509-UD-Q4_K_XL.gguf"
MODEL="/models/unsloth/Ministral-3-8B-Instruct-2512-GGUF-UD-Q4_K_XL/Ministral-3-8B-Instruct-2512-UD-Q4_K_XL.gguf"

DEVICES="--device /dev/dri/card0:/dev/dri/card0 --device /dev/dri/renderD128:/dev/dri/renderD128 --device /dev/dri/card1:/dev/dri/card1 --device /dev/dri/renderD129:/dev/dri/renderD129 --device /dev/accel:/dev/accel"
IMAGE=llama-cpp-intel
#IMAGE=llama-cpp-vulkan

docker run --security-opt label=disable \
-it --rm -v "$MODELS_PATH":/models \
$DEVICES \
$IMAGE \
--bench -m "$MODEL" \
--n-gpu-layers 99 \
--n-cpu-moe 0 \
$@
