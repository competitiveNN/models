#!/bin/sh
# Run the Strata server for Swift 1.5 IQ3_XXS on 2x Intel Arc B580 (SYCL port).
# Everything runs inside the strata-sycl-dev container (the engine needs the
# oneAPI runtime and the GPU device). The host's strata-setup folder is mounted
# at /work inside it.
#
# Usage: ./run-swift-iq3_xxs.sh [gpu.0 | gpu.0,gpu.1 | 0 | 0,1] [--pin N]
#   gpu.0        one GPU (default).
#   --pin N      pin the engine's CPU expert pool to N physical cores
#                (--pool-affinity p-cores, host thread on first core). The pool
#                serves the experts the card cannot hold, so more workers help
#                when the context is long.
#   gpu.0,gpu.1  both GPUs as a layer split: each card holds its own layers'
#                expert cache (measured 3504 + 2744 slots, 5.70 + 5.11 GiB).
#   0 / 0,1      bare numbers work too. Any card list the server accepts.
#
# Which is faster depends on --max-context in strata-src/strata-swift-iq3_xxs.json.
# Measured 2026-10-19/20 on engine 0.1.45 (--kv int8, --expert-cache-per-layer,
# --spec 4, MTP on, thinking off):
#   --max-context 32768   1 GPU 36-46 tok/s, 2 GPUs 29-31 tok/s
#   --max-context 128000  1 GPU 25-32 tok/s, 2 GPUs 28-38 tok/s
#   --max-context 131072  1 GPU 20-25 tok/s, 2 GPUs 30-32 tok/s
# The whole --max-context sits in VRAM as KV from the start, so a long context
# leaves the one card less room for experts. The two cards split the layers
# (and with them the KV), so from 128000 up the split wins.
#
# Uses podman directly: the host's `docker` is a shim that runs podman via
# flatpak-spawn, which only resolves on the host, not inside a toolbox.
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"

# The GPU spec unless the first word is a flag (then it stays for the flag loop).
SPEC="gpu.0"
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then
    SPEC="$1"
    if [ $# -gt 0 ]; then shift 2>/dev/null || true; fi
fi
# "gpu.0,gpu.1" -> "0,1" (the server's --gpu takes nvidia-smi-style numbers)
GPUS="$(printf '%s\n' "$SPEC" | sed 's/gpu\.//g')"
if ! printf '%s\n' "$GPUS" | grep -Eq '^[0-9]+(,[0-9]+)*$'; then
    echo "run-swift-iq3_xxs.sh: bad GPU spec '$SPEC' (want gpu.0 or gpu.0,gpu.1)" >&2
    exit 2
fi

# --pin N: rewrite the config's --pool-workers for a per-run CPU core pin.
PIN=""
while [ $# -gt 0 ]; do
    if [ "$1" = "--pin" ] && [ -z "${2:-}" ]; then
        echo "run-swift-iq3_xxs.sh: --pin needs a count (e.g. --pin 4)" >&2
        exit 2
    fi
    case "$1" in
        --pin) PIN="$2"; shift 2 ;;
        --pin=*) PIN="${1#--pin=}"; shift ;;
        *) echo "run-swift-iq3_xxs.sh: bad argument '$1' (want --pin N)" >&2; exit 2 ;;
    esac
done
if [ -n "$PIN" ] && ! printf '%s\n' "$PIN" | grep -Eq '^[0-9]+$'; then
    echo "run-swift-iq3_xxs.sh: bad --pin value '$PIN' (want a number)" >&2
    exit 2
fi

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
# The binary that RUNS is the AOT one on a Battlemage card (sycl/serve/strata-sycl-direct.sh
# prefers it: the AOT build carries the bmg-g21 XMX kernel set, the JIT one the sub-group 8
# Alchemist kernels that Battlemage skips).  So read the AOT binary first: reading only the
# JIT tree reported the tree's version, because that tree is never built.
for BINPATH in build-sycl-aot/strata build-sycl/strata; do
    [ -n "$MAJMIN" ] || break
    [ -x "$SRC/$BINPATH" ] || continue
    VERSION="$(strings -a "$SRC/$BINPATH" 2>/dev/null | sed -n "s/^\(${MAJMIN}\.[0-9][0-9]*\(\.[0-9][0-9]*\)\{0,1\}\)\$/\1/p" | head -1 || true)"
    [ -n "$VERSION" ] && break
done
[ -n "$VERSION" ] || VERSION="$TREE_VER"
# say so when the running engine is not the tree's release, else the number misleads
TREE_NOTE=""
if [ -n "$VERSION" ] && [ -n "$TREE_VER" ] && [ "$VERSION" != "$TREE_VER" ]; then
    TREE_NOTE=", source tree $TREE_VER"
fi
# the number alone misleads when the checkout is not the newest tag (a tree at 0.1.44.1 read like a wrong 0.1.45):
# say which commit is checked out and which tag is newest
STATE=""
if command -v git >/dev/null 2>&1 && [ -d "$SRC/.git" ]; then
    AT="$(git -C "$SRC" describe --tags --always 2>/dev/null || true)"
    NEWEST="$(git -C "$SRC" tag --sort=-v:refname 2>/dev/null | head -1 || true)"
    if [ -n "$AT" ] && [ -n "$NEWEST" ] && [ "$AT" != "$NEWEST" ]; then
        STATE=", checkout $AT (newest tag $NEWEST)"
    fi
fi
echo "strata ${VERSION:-unknown} (SYCL engine, GPU $GPUS)$TREE_NOTE$STATE"

# Build a run-scoped config copy when --pin was given so the repo's canonical
# config stays untouched; the mount makes /work/<cfg> visible inside the container.
# The config follows the GPU count: the 2-GPU arm is the SHIPPED one (the layer split,
# --expert-cache-per-layer, the measured 2x B580 configuration); the 1-GPU arm is the
# single-card config.  Before this, both arms ran the 1-GPU config with --gpu on the
# command line, which is not the configuration the 2-GPU numbers were measured on.
case "$GPUS" in
    *,*) CFG="strata-swift-iq3_xxs-2gpu-clean.json" ;;
    *)  CFG="strata-swift-iq3_xxs.json" ;;
esac
if [ ! -f "$ROOT/strata-src/$CFG" ]; then
    echo "run-swift-iq3_xxs.sh: the config $CFG is missing" >&2
    exit 2
fi
if [ -n "$PIN" ]; then
    rm -f "$ROOT/strata-src/strata-swift-iq3_xxs-pin"*.json >/dev/null 2>&1 || true
    sed "/--pool-workers/{n;s/\"[0-9]\+\"/\"$PIN\"/}" "$ROOT/strata-src/$CFG" \
        > "$ROOT/strata-src/strata-swift-iq3_xxs-pin${PIN}.json"
    CFG="strata-swift-iq3_xxs-pin${PIN}.json"
fi

exec docker run --rm --privileged --device /dev/dri \
    --name strata-server --replace \
    --network host \
    -v "$ROOT:/work" \
    -v "/home/fra/data/models/gguf/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF:/gguf:ro" \
    strata-sycl-dev \
    "cd /work/strata-src && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1; exec .venv/bin/python sycl/serve/server_intel.py --engine strata --config /work/strata-src/$CFG --gpu '$GPUS' --port 8081"
