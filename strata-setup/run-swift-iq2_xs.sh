#!/bin/sh
# Run the Strata server for Swift 1.5 IQ2_XS on Intel Arc B580 (SYCL port).
# Everything runs inside the strata-sycl-dev container (the engine needs the
# oneAPI runtime and the GPU device). The host's strata-setup folder is mounted
# at /work inside it.
#
# Usage: ./run-swift-iq2_xs.sh [--pin N]
#   --pin N      pin the engine's CPU expert pool to N physical cores
#                (--pool-affinity p-cores, host thread on first core).
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/strata-src"

# --pin N: rewrite the config's --pool-workers for a per-run CPU core pin.
PIN=""
while [ $# -gt 0 ]; do
    if [ "$1" = "--pin" ] && [ -z "${2:-}" ]; then
        echo "run-swift-iq2_xs.sh: --pin needs a count (e.g. --pin 4)" >&2
        exit 2
    fi
    case "$1" in
        --pin) PIN="$2"; shift 2 ;;
        --pin=*) PIN="${1#--pin=}"; shift ;;
        *) echo "run-swift-iq2_xs.sh: bad argument '$1' (want --pin N)" >&2; exit 2 ;;
    esac
done
if [ -n "$PIN" ] && ! printf '%s\n' "$PIN" | grep -Eq '^[0-9]+$'; then
    echo "run-swift-iq2_xs.sh: bad --pin value '$PIN' (want a number)" >&2
    exit 2
fi
# Report the version of the engine that will actually RUN, not of the source tree: the
# image binary can be built from a different release than $SRC is checked out at -- the
# container binary came from the v0.1.45 worktree while $SRC sits on 0.1.44.1. The engine
# bakes it in as STRATA_VERSION at compile time (generate.cpp prints "engine <ver>").
TREE_VER="$(sed -n 's/^project(strata VERSION \([0-9.][0-9.]*\).*/\1/p' "$SRC/CMakeLists.txt" 2>/dev/null | head -1 || true)"
# the engine binary also holds unrelated version strings (e.g. 0.24.0), so anchor the
# search to the tree's major.minor: that picks the engine version and nothing else
MAJMIN="$(printf '%s\n' "$TREE_VER" | cut -d. -f1,2)"
VERSION=""
if [ -n "$MAJMIN" ] && [ -x "$SRC/build-sycl/strata" ]; then
    VERSION="$(strings -a "$SRC/build-sycl/strata" 2>/dev/null | sed -n "s/^\(${MAJMIN}\.[0-9][0-9]*\(\.[0-9][0-9]*\)\{0,1\}\)\$/\1/p" | head -1 || true)"
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
echo "strata ${VERSION:-unknown} (SYCL engine)$TREE_NOTE$STATE"

# Build a run-scoped config copy when --pin was given so the repo's canonical
# config stays untouched; the mount makes /work/<cfg> visible inside the container.
CFG="strata-swift-iq2_xs.json"
if [ -n "$PIN" ]; then
    rm -f "$ROOT/strata-src/strata-swift-iq2_xs-pin"*.json >/dev/null 2>&1 || true
    CFG="strata-swift-iq2_xs-pin${PIN}.json"
    sed "/--pool-workers/{n;s/\"[0-9]\+\"/\"$PIN\"/}" "$ROOT/strata-src/strata-swift-iq2_xs.json" > "$ROOT/strata-src/$CFG"
fi

docker run --rm --privileged --device /dev/dri \
    --name strata-server \
    --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG --port 8081"