#!/bin/bash
# Restart the strata server container with a given config file and port.
# Usage: PORT=8081 ./tp-restart.sh <config-name-without-.json>
CFG="${1:?config name, e.g. strata-swift-iq3_xxs}"
PORT="${PORT:-8081}"
ROOT="/var/home/fra/dev/models/strata-setup"
/var/home/fra/bin/docker rm -f strata-server >/dev/null 2>&1
sleep 2
/var/home/fra/bin/docker run -d --privileged --device /dev/dri \
  --name strata-server --replace \
  --network host \
  -v "$ROOT:/work" \
  -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
  --entrypoint /bin/bash \
  strata-sycl-dev \
  -c "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG.json --port $PORT" \
  > tp-restart.out 2>&1
for i in $(seq 1 120); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | /usr/bin/grep -q '"loaded": true'; then
    echo "ready after ${i}x2s: $CFG on port $PORT"
    exit 0
  fi
  sleep 2
done
echo "NOT READY after 240s: $CFG on port $PORT"
exit 1
