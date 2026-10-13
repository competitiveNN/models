#!/bin/sh
# 2-GPU trial: start the server with env overrides, fire several sequential requests, record.
#   ./trials.sh TAG "VAR=val VAR2=val2" REQ_COUNT
# The env overrides are merged into strata-swift-iq3_xxs.json (they win over the config's own).
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
TAG="${1:-trial}"
ENVV="${2:-}"
NREQ="${3:-4}"
SRC="$ROOT/strata-src"
CFG="$SRC/strata-swift-iq3_xxs.json"
LOG="$ROOT/trials-$TAG.out"
TMPCFG="$SRC/strata-swift-trial.json"

# write the JSON with the overrides merged in
python3 - "$CFG" "$TMPCFG" "$ENVV" <<'PY'
import json, sys
src, dst, envv = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.loads(open(src, encoding="utf-8").read())
env = dict(cfg.get("env") or {})
for kv in envv.split():
    if "=" in kv:
        k, v = kv.split("=", 1)
        env[k] = v
cfg["env"] = env
json.dump(cfg, open(dst, "w"), indent=1)
PY

: > "$LOG"
nohup docker run --rm --privileged --device /dev/dri \
    --name strata-trial --replace --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/strata-swift-trial.json --port 8081" \
    >> "$LOG" 2>&1 &
SRV=$!
echo "=== trial $TAG env: $ENVV (pid $SRV) ===" | tee -a "$LOG"

ready=0
for i in $(seq 1 60); do
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
    out=$(curl -s --max-time 600 -X POST http://127.0.0.1:8081/v1/chat/completions \
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

# sequential, varying sizes: short, medium, long, thinking-heavy
req 20 "Say hello in one short sentence."
[ "$NREQ" -ge 2 ] && req 60 "Write a haiku about the sea."
[ "$NREQ" -ge 3 ] && req 120 "Explain what a transformer is, in two paragraphs."
[ "$NREQ" -ge 4 ] && req 200 "Tell me a story about a robot learning to paint, with dialogue."

# engine log signals
echo "=== engine signals ===" | tee -a "$LOG"
grep -c 'no progress for' "$SRC/strata-swift-iq3_xxs.log" | sed 's/^/stalls: /' | tee -a "$LOG"
tail -3 "$SRC/strata-swift-iq3_xxs.log" | tee -a "$LOG"

kill "$SRV" 2>/dev/null || true
wait "$SRV" 2>/dev/null || true
docker rm -f strata-trial >/dev/null 2>&1
echo "----- done ($TAG) -----" | tee -a "$LOG"
