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
MODEL_SPECIFIED=false
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
      MODEL_SPECIFIED=true
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

# If model not specified, try to find the first available one via API
if [ "$MODEL_SPECIFIED" = false ]; then
    echo "No model specified, querying API for available models..."
    FIRST_MODEL=$(python3 -c "from openai import OpenAI; 
try:
    client = OpenAI(api_key='$KEY', base_url='$URL');
    models = client.models.list().data;
    print(models[0].id if models else '')
except Exception:
    print('')" 2>/dev/null)
    
    if [ -n "$FIRST_MODEL" ]; then
        MODEL="$FIRST_MODEL"
        echo "Using first available model: $MODEL"
    else
        echo "Failed to query models from API. Using fallback default: gemma3-4b-cw"
        MODEL="gemma3-4b-cw"
    fi
fi

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
