#!/bin/bash
# Benchmark a strata SYCL server config: start it, fire N sequential requests, report tok/s.
# Usage: ./bench-strata.sh <config-json> <bin-name> <tag> [nreq]
#   bin-name: "jit" (build-sycl/strata) or "aot" (build-sycl-aot/strata)
# Writes bench-<tag>.out and leaves the server stopped.
set -u
# shellcheck disable=SC2034
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/runs"
CFG="${1:?config json name (without .json)}"
BIN="${2:?jit|aot}"
TAG="${3:?tag}"
NREQ="${4:-6}"
LOG="$ROOT/runs/bench-$TAG.out"
PORT=8081


: > "$LOG"
echo "== bench $TAG: cfg=$CFG bin=$BIN reqs=$NREQ $(date -Is)" | tee -a "$LOG"

# start server (docker, rootless; the `docker` shim on this host is flatpak-spawn based and broken)
docker rm -f strata-bench >/dev/null 2>&1
docker run -d --privileged --device /dev/dri \
  --name strata-bench --replace --network host \
  -w /work/strata-src \
  -v "$ROOT:/work" \
  -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
  -e LD_LIBRARY_PATH=/opt/intel/oneapi/compiler/2026.2/lib:/opt/intel/oneapi/mkl/2026.2/lib:/opt/intel/oneapi/redist/lib \
  -e ZE_FLAT_DEVICE_MEMORY=1 \
  -e STRATA_VERIFY_DEVICE_PLAN=0 \
  -e STRATA_VERIFY_NO_HOST=0 \
  -e STRATA_WINDOW_SYNC=1 \
  -e STRATA_STAGE_TRIM=1 \
  -e STRATA_PREFILL_MMQ=0 \
  -e STRATA_DECODE_TIMING=1 \
  -e STRATA_SPLIT_HEADROOM=0 \
  -e STRATA_VERIFY_PIPE=0 \
  -e STRATA_RING_TIMEOUT_S=600 \
  -e STRATA_SPLIT_WAIT_MS=600000 \
  -e STRATA_VERIFY_DRAIN_TIMEOUT_MS=60000 \
  localhost/strata-server:latest \
  -c "cd /work/strata-src && python3 sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG.json --port $PORT" \
  >> "$LOG" 2>&1
# `docker run -d` DETACHES: the client returns the container id and exits, so the
# client's PID is gone while the container keeps running.  The liveness probe must
# therefore ask docker for the container's state, not `kill -0` the client pid (the
# old check aborted every run with "SERVER DIED DURING START" while the server was
# in fact loading the model).
ready=0
for i in $(seq 1 300); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"loaded": true'; then
    ready=1; break; fi
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^strata-bench$'; then
    echo "SERVER DIED DURING START" | tee -a "$LOG"; break; fi
  sleep 2
done
if [ "$ready" != "1" ]; then
  echo "ABORT: not ready after 600s" | tee -a "$LOG"
  tail -30 "$LOG"
  docker rm -f strata-bench >/dev/null 2>&1; exit 1
fi
echo "ready after $((i*2))s" | tee -a "$LOG"
# let the cache warm
sleep 8

tot=0; n=0; fails=0
for i in $(seq 1 "$NREQ"); do
  mt=$((120 + i*10))
  t0=$(date +%s.%N)
  out=$(curl -s -m 600 -X POST http://127.0.0.1:$PORT/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"swift-1.5-iq3_xxs\",\"messages\":[{\"role\":\"user\",\"content\":\"Write a short story about a robot learning to paint, step $i.\"}],\"max_tokens\":$mt,\"temperature\":0.6,\"enable_thinking\":false}" 2>>"$LOG")
  t1=$(date +%s.%N)
  line=$(printf '%s' "$out" | python3 -c "
import sys, json
try: d = json.load(sys.stdin)
except Exception as e:
    print('FAIL notjson'); sys.exit(0)
c = d.get('choices') or [{}]; c = c[0] if c else {}
u = d.get('usage') or {}
t = d.get('timings') or {}
if not c.get('finish_reason'):
    print('FAIL finish=' + repr(c.get('finish_reason'))); sys.exit(0)
pt = u.get('prompt_tokens',0); ct = u.get('completion_tokens',0)
eng = t.get('predicted_per_second',0)
print(f'OK prompt={pt} completion={ct} eng_tps={eng:.1f}')
")
  dt=$(python3 -c "print(f'{float('$t1')-float('$t0'):.1f}')")
  echo "req $i mt=$mt wall=${dt}s: $line" | tee -a "$LOG"
  case "$line" in
    OK*) n=$((n+1)); tot=$(python3 -c "print($tot + $(echo "$line" | sed -n 's/.*completion=\([0-9]*\).*/\1/p'))");;
    *) fails=$((fails+1));;
  esac
done

echo "=== engine tail ===" | tee -a "$LOG"
tail -4 "$ROOT/runs/strata-swift-iq3_xxs.log" | sed 's/^/  /' | tee -a "$LOG"
echo "== $TAG done: ok=$n fail=$fails total_tokens=$tot $(date -Is)" | tee -a "$LOG"

docker rm -f strata-bench >/dev/null 2>&1