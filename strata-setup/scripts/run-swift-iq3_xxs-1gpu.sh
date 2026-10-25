#!/bin/sh
# ONE Intel Arc B580: Swift 1.5 IQ3_XXS (SYCL port), on port 8082.
#
# The one-card arm of the rig: the same model, the same engine, one GPU.  It is the
# control for "is the layer split worth it" - measured 2026-10-19/20, one card is faster
# below ~128k of context and slower above it (the whole KV sits in VRAM from the start,
# so a long context leaves the single card less room for experts).
#
# The config is derived by scripts/run-strata.sh from the single-card template, so this
# script cannot go stale pointing at a config that was renamed or deleted.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=strata-swift-iq3_xxs-1gpu-reg
PORT=8082
export BASE PORT
exec "$ROOT/scripts/run-strata.sh" strata-swift-iq3_xxs-1gpu
