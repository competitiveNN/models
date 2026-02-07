#!/bin/bash

# Defaults
URL="http://localhost:8000/v3"
KEY="abc"
MODEL="qwen3-14b"
REQUESTS=1
CONCURRENCY=1
TOKENS=250

# Activate virtual env if it exists
[ -d ".venv" ] && source .venv/bin/activate

# Command detection (default to 'bench')
OPTS=()
CMD="bench"
if [[ "$1" == "list" || "$1" == "optimize" || "$1" == "context" ]]; then
    CMD=$1
    shift
fi

# Positional assignment for optional overrides
# After shift, $1 is the first arg after the command (e.g., URL)
URL=${1:-$URL}
KEY=${2:-$KEY}
MODEL=${3:-$MODEL}

case "$CMD" in
    list)
        OPTS+=(--list)
        ;;
    optimize)
        OPTS+=(--optimize)
        # Use 4th arg for max tokens if provided
        OPTS+=(--max-tokens "${4:-$TOKENS}")
        ;;
    context)
        OPTS+=(--context)
        echo "Starting Max Context Discovery for $MODEL at $URL..."
        ;;
    bench)
        REQ=${4:-$REQUESTS}
        CON=${5:-$CONCURRENCY}
        TOK=${6:-$TOKENS}
        OPTS+=(--requests "$REQ" --concurrency "$CON" --max-tokens "$TOK")
        echo "Benchmarking $URL... (Model: $MODEL, Requests: $REQ, Concurrency: $CON, Tokens: $TOK)"
        ;;
esac

python3 bench.py --url "$URL" --api-key "$KEY" --model "$MODEL" "${OPTS[@]}"
