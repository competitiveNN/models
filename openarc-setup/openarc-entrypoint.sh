#!/bin/bash

. /app/.venv/bin/activate
# uv pip install sentencepiece # for llama2
uv pip install --reinstall transformers # for qwen3.5 support (hotfix)
exec openarc "$@"
