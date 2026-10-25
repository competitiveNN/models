#!/bin/sh
# 2x Intel Arc B580, EAGER verify: no window-graph capture, run() replays the body.
#
# A DIAGNOSTIC arm, not a candidate to ship: STRATA_VERIFY_EAGER=1 runs each window on the
# queue instead of as a captured graph, so every kernel launch is a separate submission.
# It is here to read the per-stage host clocks the profiler cannot get from a graph (the
# stage stamps become host-side waits), and to check whether the graph capture itself is
# worth anything - compare it against scripts/run-swift-iq3_xxs-dp0.sh.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=strata-swift-iq3_xxs-2gpu-clean
PORT=8081
export BASE PORT
exec "$ROOT/scripts/run-strata.sh" strata-swift-iq3_xxs-2gpu-eager \
    STRATA_VERIFY_EAGER=1
