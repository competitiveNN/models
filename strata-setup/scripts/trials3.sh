#!/bin/sh
# Sequential-request trial using an existing run script (no JSON rewrite).
#   ./trials3.sh RUNSCRIPT TAG NREQ
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNSCRIPT="$1"
TAG="$2"
NREQ="${3:-4}"
PORT="${PORT:-8082}"
LOG="$ROOT/trials3-$TAG.out"
SRC="$ROOT/strata-src"

: > "$LOG"
# The run script's `docker run --replace` SIGTERMs any previous strata-server container and the engine
# then takes a while to unwind (releasing VRAM). Starting too early makes the new engine allocate from
# less free VRAM (seen: 1497 -> 585 MiB free), which shrinks the expert cache and slows every request.
for _ in $(seq 1 60); do
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx strata-server || break
    sleep 2
done
docker rm -f strata-server >/dev/null 2>&1 || true
nohup "$ROOT/$RUNSCRIPT" > "$LOG" 2>&1 &
SRV=$!
echo "=== trial3 $TAG run=$RUNSCRIPT (pid $SRV) ===" | tee -a "$LOG"

ready=0
for i in $(seq 1 70); do
    if grep -q "ready: http" "$LOG" 2>/dev/null; then ready=1; break; fi
    if ! kill -0 "$SRV" 2>/dev/null; then echo "SERVER DIED DURING START" | tee -a "$LOG"; break; fi
    sleep 5
done
if [ "$ready" != "1" ]; then
    echo "ABORT: not ready" | tee -a "$LOG"
    kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null
    tail -25 "$LOG"
    exit 1
fi
echo "ready after $((i * 5))s" | tee -a "$LOG"
sleep 5

req() {
    n="$1"; shift; msg="$1"
    echo "----- req max_tokens=$n -----" | tee -a "$LOG"
    out=$(curl -s --max-time 900 -X POST http://127.0.0.1:$PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"$msg\"}],\"max_tokens\":$n,\"temperature\":0.6}" 2>>"$LOG")
    echo "$out" | python3 -c "
import sys, json
try: d = json.load(sys.stdin)
except Exception:
    print('RAW (not json):', sys.stdin.read()[:300]); sys.exit(0)
c = d.get('choices') or [{}]
c = c[0] if c else {}
u = d.get('usage') or {}
print('tokens:', u.get('completion_tokens'), 'prompt:', u.get('prompt_tokens'),
      'finish:', c.get('finish_reason'), 'err:', d.get('error'))
m = (c.get('message') or {}).get('content')
if m: print('content:', m[:80].replace(chr(10), ' '))
" 2>>"$LOG" | tee -a "$LOG"
}

req 20 "Say hello in one short sentence."
[ "$NREQ" -ge 2 ] && req 60 "Write a haiku about the sea."
[ "$NREQ" -ge 3 ] && req 120 "Explain what a transformer is, in two paragraphs."
[ "$NREQ" -ge 4 ] && req 200 "Tell me a story about a robot learning to paint, with dialogue."

echo "=== engine signals ===" | tee -a "$LOG"
# The engine log name follows the run script (run-X.sh -> strata-X.json -> strata-X.log); the default
# config is strata-swift-iq3_xxs.json. Reading the wrong log reports another run's stall count.
CFG_LOG=$(sed -n 's/.*--config \/work\/strata-src\/\([^"]*\)\.json.*/\1/p' "$ROOT/$RUNSCRIPT" 2>/dev/null | head -1)
[ -n "$CFG_LOG" ] || CFG_LOG=strata-swift-iq3_xxs
grep -c 'no progress for' "$SRC/$CFG_LOG.log" 2>/dev/null | sed 's/^/stalls: /' | tee -a "$LOG"
tail -3 "$SRC/$CFG_LOG.log" 2>/dev/null | tee -a "$LOG"

kill "$SRV" 2>/dev/null || true
wait "$SRV" 2>/dev/null || true
# Wait for the container to actually release its VRAM before a next trial starts (--replace would
# otherwise find it mid-shutdown).
for _ in $(seq 1 60); do
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx strata-server || break
    sleep 2
done
echo "----- done ($TAG) -----" | tee -a "$LOG"