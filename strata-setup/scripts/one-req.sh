#!/bin/sh
# Single-request trial: start the server, fire ONE request, record engine log.
#   ./one-req.sh TAG "ENVVARS" MAX_TOKENS
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-one}"
ENVV="${2:-}"
MT="${3:-200}"
SRC="$ROOT/strata-src"
CFG="$SRC/strata-swift-iq3_xxs.json"
LOG="$ROOT/one-$TAG.out"
TMPCFG="$SRC/strata-swift-trial.json"

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
    --name strata-one --replace --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/strata-swift-trial.json --port 8081" \
    >> "$LOG" 2>&1 &
SRV=$!
echo "=== one-req $TAG env: $ENVV (pid $SRV) ===" | tee -a "$LOG"

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

echo "----- req max_tokens=$MT -----" | tee -a "$LOG"
curl -s --max-time 900 -X POST http://127.0.0.1:8081/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"Tell me a story about a robot learning to paint, with dialogue.\"}],\"max_tokens\":$MT,\"temperature\":0.6}" 2>>"$LOG" | tee -a "$LOG"

echo "=== engine signals ===" | tee -a "$LOG"
grep -c 'no progress for' "$SRC/strata-swift-iq3_xxs.log" | sed 's/^/stalls: /' | tee -a "$LOG"
tail -3 "$SRC/strata-swift-iq3_xxs.log" | tee -a "$LOG"

kill "$SRV" 2>/dev/null || true
wait "$SRV" 2>/dev/null || true
docker rm -f strata-one >/dev/null 2>&1
echo "----- done ($TAG) -----" | tee -a "$LOG"