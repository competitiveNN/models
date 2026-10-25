#!/bin/sh
# 2x Intel Arc B580, EAGER verify and the device-plan path off.
#
# The diagnostic arm with STRATA_VERIFY_DEVICE_PLAN=0 as well: the device-plan path is
# already off in the shipped config on this tree, so this is the eager arm with that
# stated explicitly (it used to be a separate thing).
#
# A DIAGNOSTIC arm, not a candidate to ship - see scripts/run-swift-iq3_xxs-eager.sh.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=strata-swift-iq3_xxs-2gpu-clean
PORT=8081
export BASE PORT
exec "$ROOT/scripts/run-strata.sh" strata-swift-iq3_xxs-2gpu-dp0eager \
    STRATA_VERIFY_DEVICE_PLAN=0 STRATA_VERIFY_EAGER=1
