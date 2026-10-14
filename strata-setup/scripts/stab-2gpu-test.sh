#!/bin/sh
# 2-GPU stability test for IQ3_XXS on 2x B580: run the server, then fire several
# sequential requests of different sizes and record the results.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/stab-2gpu-test.out"
: > "$LOG"

# 1) start the server in the background
nohup "$ROOT/run-swift-iq3_xxs.sh" > "$LOG" 2>&1 &
SRV=$!
echo "server pid $SRV" | tee -a "$LOG"

# 2) wait for it to be ready (up to ~300 s)
for i in $(seq 1 60); do
    if grep -q "ready: http" "$LOG" 2>/dev/null; then
        echo "ready after ${i}0s" | tee -a "$LOG"
        break
    fi
    sleep 5
done

# 3) fire sequential requests: short, medium, long, thinking-heavy
req() {
    n="$1"; shift
    msg="$1"
    echo "----- req: $msg (max_tokens=$n) -----" | tee -a "$LOG"
    curl -s --max-time 600 -X POST http://127.0.0.1:8081/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"$msg\"}],\"max_tokens\":$n,\"temperature\":0.6}" \
        | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('choices',[{}])[0]; u=d.get('usage',{}); print('tokens:', u.get('completion_tokens'), 'prompt:', u.get('prompt_tokens'), 'err:', c.get('finish_reason'), d.get('error'))" 2>> "$LOG" | tee -a "$LOG"
}

req 20 "Say hello in one short sentence."
req 60 "Write a haiku about the sea."
req 120 "Explain what a transformer is, in two paragraphs."
req 200 "Tell me a story about a robot learning to paint, with dialogue."

# 4) stop
kill "$SRV" 2>/dev/null || true
wait "$SRV" 2>/dev/null || true
echo "----- done -----" | tee -a "$LOG"