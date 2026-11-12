#!/bin/bash
# Reproducible benchmark: parses engine log for decode/prefill tok/s + VRAM, outputs JSON
# Usage: ./bench-reproducible.sh <config-json> <tag>
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="${1:?config json name (without .json)}"
TAG="${2:?tag}"
LOG="$ROOT/runs/bench-$TAG.out"
ENGINE_LOG="$ROOT/runs/$CFG.log"
PORT=8081
trap 'docker rm -f strata-bench >/dev/null 2>&1' EXIT

: > "$LOG"
echo "== bench $TAG: cfg=$CFG $(date -Is)" | tee -a "$LOG"

docker rm -f strata-bench >/dev/null 2>&1
docker run -d --privileged --device /dev/dri \
  --name strata-bench --replace --network host \
  -w /work/strata-src \
  -v "$ROOT:/work" \
  -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
  -e LD_LIBRARY_PATH=/opt/intel/oneapi/compiler/2026.2/lib:/opt/intel/oneapi/mkl/2026.2/lib:/opt/intel/oneapi/redist/lib:/opt/intel/oneapi/level-zero/lib64:/opt/intel/oneapi/umf/1.2/lib \
  -e ZE_FLAT_DEVICE_MEMORY=1 \
  -e STRATA_VERIFY_DRAIN_TIMEOUT_MS=120000 \
  -e STRATA_COPY_ENGINE=0 \
  localhost/strata-server:latest \
  -c "cd /work/strata-src && python3 sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG.json --port $PORT" \
  >> "$LOG" 2>&1

ready=0
for i in $(seq 1 300); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"loaded": true'; then
    ready=1; break; fi
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^strata-bench$'; then
    echo "SERVER DIED" | tee -a "$LOG"; break; fi
  sleep 2
done
if [ "$ready" != "1" ]; then
  echo '{"error":"not_ready"}' | tee "$ROOT/runs/bench-$TAG.json"
  exit 1
fi
echo "ready after $((i*2))s" | tee -a "$LOG"
sleep 5

# Parse VRAM from engine log
VRAM_FREE=$(grep -oP '\d+ MiB of VRAM free' "$ENGINE_LOG" 2>/dev/null | tail -1 | grep -oP '^\d+' || echo "0")

# Run 3 requests, capture timings
RESULTS=""
for i in 1 2 3; do
  t0=$(date +%s.%N)
  out=$(curl -s -m 300 -X POST http://127.0.0.1:$PORT/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"Write a short story about a robot, request $i.\"}],\"max_tokens\":64,\"temperature\":0.6,\"enable_thinking\":false}" 2>>"$LOG")
  t1=$(date +%s.%N)
  dt=$(python3 -c "print(f'{float('$t1')-float('$t0'):.2f}')")
  # Parse engine stats from response
  usage=$(echo "$out" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    u = d.get('usage', {})
    pt = u.get('prompt_tokens', 0)
    ct = u.get('completion_tokens', 0)
    print(f'{pt} {ct}')
except:
    print('0 0')
" 2>/dev/null)
  pt=$(echo $usage | cut -d' ' -f1)
  ct=$(echo $usage | cut -d' ' -f2)
  echo "req $i wall=${dt}s prompt=$pt completion=$ct" | tee -a "$LOG"
  RESULTS="$RESULTS{\"wall_s\":$dt,\"prompt_tokens\":$pt,\"completion_tokens\":$ct},"
done

# Parse engine decode/prefill from log tail
ENGINE_STATS=$(grep -E "tok/s|decode|prefill" "$ENGINE_LOG" 2>/dev/null | tail -5)

# Output JSON summary
cat > "$ROOT/runs/bench-$TAG.json" << EOF
{
  "tag": "$TAG",
  "config": "$CFG",
  "timestamp": "$(date -Is)",
  "vram_free_mib": $VRAM_FREE,
  "requests": [$RESULTS],
  "engine_log_tail": "$ENGINE_STATS"
}
EOF
echo "Wrote $ROOT/runs/bench-$TAG.json" | tee -a "$LOG"
cat "$ROOT/runs/bench-$TAG.json"
echo ""
echo "== $TAG done $(date -Is)" | tee -a "$LOG"