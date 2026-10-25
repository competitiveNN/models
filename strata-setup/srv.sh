#!/bin/bash
# Start the strata SYCL server in the background and keep it up.
# Usage: ./srv.sh <config-json> <bin-name>
#   bin-name: jit | aot
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/runs"
CFG="$1"; BIN="$2"
PORT="${PORT:-8081}"
case "$BIN" in
  jit) BINPATH="build-sycl/strata" ;;
  aot) BINPATH="build-sycl-aot/strata" ;;
  *) echo "bad bin $BIN"; exit 2 ;;
esac
SRC="$ROOT/strata-src"
# Report the version of the engine that will actually RUN, not of the source tree: the
# image binary can be built from a different release than $SRC is checked out at -- the
# container binary came from the v0.1.45 worktree while $SRC sits on 0.1.44.1. The engine
# bakes it in as STRATA_VERSION at compile time (generate.cpp prints "engine <ver>").
TREE_VER="$(sed -n 's/^project(strata VERSION \([0-9.][0-9.]*\).*/\1/p' "$SRC/CMakeLists.txt" 2>/dev/null | head -1 || true)"
# the engine binary also holds unrelated version strings (e.g. 0.24.0), so anchor the
# search to the tree's major.minor: that picks the engine version and nothing else
MAJMIN="$(printf '%s\n' "$TREE_VER" | cut -d. -f1,2)"
VERSION=""
if [ -n "$MAJMIN" ] && [ -x "$SRC/$BINPATH" ]; then
    VERSION="$(strings -a "$SRC/$BINPATH" 2>/dev/null | sed -n "s/^\(${MAJMIN}\.[0-9][0-9]*\(\.[0-9][0-9]*\)\{0,1\}\)\$/\1/p" | head -1 || true)"
fi
[ -n "$VERSION" ] || VERSION="$TREE_VER"
# say so when the running engine is not the tree's release, else the number misleads
TREE_NOTE=""
if [ -n "$VERSION" ] && [ -n "$TREE_VER" ] && [ "$VERSION" != "$TREE_VER" ]; then
    TREE_NOTE=", source tree $TREE_VER"
fi
# the number alone misleads when the checkout is not the newest tag: say which commit it is on
STATE=""
if command -v git >/dev/null 2>&1 && [ -d "$SRC/.git" ]; then
    AT="$(git -C "$SRC" describe --tags --always 2>/dev/null || true)"
    NEWEST="$(git -C "$SRC" tag --sort=-v:refname 2>/dev/null | head -1 || true)"
    if [ -n "$AT" ] && [ -n "$NEWEST" ] && [ "$AT" != "$NEWEST" ]; then
        STATE=", checkout $AT (newest tag $NEWEST)"
    fi
fi
echo "strata ${VERSION:-unknown} (SYCL engine, $BIN, port $PORT)$TREE_NOTE$STATE"
podman rm -f strata-srv >/dev/null 2>&1
podman run -d --privileged --device /dev/dri --name strata-srv --replace --network host \
  -w /work/strata-src \
  -v "$ROOT:/work" \
  -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
  localhost/strata-sycl-dev \
  -lc "source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG.json --port $PORT" \
  > "$ROOT/runs/srv-$CFG-$BIN.log" 2>&1 &
echo "server pid $! (cfg=$CFG bin=$BIN) -> $ROOT/srv-$CFG-$BIN.log"
for i in $(seq 1 120); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"loaded": true'; then
    echo "ready after $((i*2))s"; exit 0; fi
  sleep 2
done
echo "NOT READY"; tail -20 "$ROOT/runs/srv-$CFG-$BIN.log"; exit 1