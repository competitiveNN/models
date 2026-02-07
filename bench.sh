#!/bin/bash

# Defaults
URL="http://localhost:8000/v3"
KEY="abc"
MODEL="gemma3-4b-cw"
REQUESTS=1
CONCURRENCY=1
TOKENS=250
CMD="bench"

# Activate virtual env if it exists
[ -d ".venv" ] && source .venv/bin/activate

# Parse flags and commands
while [[ $# -gt 0 ]]; do
  case $1 in
    -u|--url)
      URL="$2"
      shift 2
      ;;
    -k|--key)
      KEY="$2"
      shift 2
      ;;
    -m|--model)
      MODEL="$2"
      shift 2
      ;;
    -r|--requests)
      REQUESTS="$2"
      shift 2
      ;;
    -c|--concurrency)
      CONCURRENCY="$2"
      shift 2
      ;;
    -t|--tokens)
      TOKENS="$2"
      shift 2
      ;;
    --list|list)
      CMD="list"
      shift
      ;;
    --optimize|optimize)
      CMD="optimize"
      shift
      ;;
    --context|context)
      CMD="context"
      shift
      ;;
    bench)
      CMD="bench"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [command] [-u URL] [-k KEY] [-m MODEL] [-r REQUESTS] [-c CONCURRENCY] [-t TOKENS]"
      echo "Commands: bench (default), list, optimize, context"
      exit 1
      ;;
  esac
done

OPTS=()
case "$CMD" in
    list)
        OPTS+=(--list)
        ;;
    optimize)
        OPTS+=(--optimize --max-tokens "$TOKENS")
        ;;
    context)
        OPTS+=(--context)
        echo "Starting Max Context Discovery for $MODEL at $URL..."
        ;;
    bench)
        OPTS+=(--requests "$REQUESTS" --concurrency "$CONCURRENCY" --max-tokens "$TOKENS")
        echo "Benchmarking $URL... (Model: $MODEL, Requests: $REQUESTS, Concurrency: $CONCURRENCY, Tokens: $TOKENS)"
        ;;
esac

python3 bench.py --url "$URL" --api-key "$KEY" --model "$MODEL" "${OPTS[@]}"
