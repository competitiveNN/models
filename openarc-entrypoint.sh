#!/bin/bash

. /app/.venv/bin/activate
# pip install sentencepiece # for llama2
exec openarc serve start
