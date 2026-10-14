#!/bin/sh
# 2-GPU stability test for IQ3_XXS on 2x B580 with STRATA_SPIN_MAX=2000000.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/stab-2gpu-spin2m.out"
: > "$LOG"

nohup "$ROOT/run-swift-iq3_xxs.sh" > "$LOG" 2>&1 &
SRV=$!
echo "server pid $SRV" | tee -a "$LOG"

ready=0
for i in $(seq 1 70); do
    if grep -q "ready: http" "$LOG" 2>/dev/null; then
        echo "ready after ${i}0s" | tee -a "$LOG"; ready=1; break
    fi
    if ! kill -0 "$SRV" 2>/dev/null; then echo "server died during start" | tee -a "$LOG"; break; fi
    sleep 5
done
if [ "$ready" != "1" ]; then echo "ABORT: not ready"; kill "$SRV" 2>/dev/null; exit 1; fi
sleep 5

req() {
    n="$1"; shift
    msg="$1"
    echo "----- req: $msg (max_tokens=$n) -----" | tee -a "$LOG"
    out=$(curl -s --max-time 600 -X POST http://127.0.0.1:8081/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"$msg\"}],\"max_tokens\":$n,\"temperature\":0.6}" 2>>"$LOG")
    echo "$out" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin)
except Exception:
    print('RAW (not json):', sys.stdin.read()[:400]); sys.exit(0)
c=d.get('choices',[{}])[0]; u=d.get('usage',{})
print('tokens:', u.get('completion_tokens'), 'prompt:', u.get('prompt_tokens'), 'finish:', c.get('finish_reason'), 'err:', d.get('error'))
m=(c.get('message') or {}).get('content')
if m: print('content:', m[:100])
" 2>>"$LOG" | tee -a "$LOG"
}

req 20 "Say hello in one short sentence."
req 60 "Write a haiku about the sea."
req 120 "Explain what a transformer is, in two paragraphs."

kill "$SRV" 2>/dev/null || true
wait "$SRV" 2>/dev/null || true
echo "----- done -----" | tee -a "$LOG"