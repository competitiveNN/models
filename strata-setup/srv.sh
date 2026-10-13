#!/bin/bash
# Start the strata SYCL server in the background and keep it up.
# Usage: ./srv.sh <config-json> <bin-name>
#   bin-name: jit | aot
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
CFG="$1"; BIN="$2"
PORT="${PORT:-8081}"
case "$BIN" in
  jit) BINPATH="build-sycl/strata" ;;
  aot) BINPATH="build-sycl-aot/strata" ;;
  *) echo "bad bin $BIN"; exit 2 ;;
esac
podman rm -f strata-srv >/dev/null 2>&1
podman run -d --privileged --device /dev/dri --name strata-srv --replace --network host \
  -w /work/strata-src \
  -v "$ROOT:/work" \
  -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
  localhost/strata-sycl-dev \
  -lc "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG.json --port $PORT" \
  > "$ROOT/srv-$CFG-$BIN.log" 2>&1 &
echo "server pid $! (cfg=$CFG bin=$BIN) -> $ROOT/srv-$CFG-$BIN.log"
for i in $(seq 1 120); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"loaded": true'; then
    echo "ready after $((i*2))s"; exit 0; fi
  sleep 2
done
echo "NOT READY"; tail -20 "$ROOT/srv-$CFG-$BIN.log"; exit 1