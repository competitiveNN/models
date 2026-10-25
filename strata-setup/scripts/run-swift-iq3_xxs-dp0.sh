#!/bin/sh
# 2x Intel Arc B580 as a layer split: Swift 1.5 IQ3_XXS (SYCL port), on port 8081.
#
# THE SHIPPED CONFIGURATION.  Both cards hold their own layers' expert cache, the KV is
# split with the layers, and the engine is the AOT build (the bmg-g21 XMX kernel set).
# It is the baseline every A/B on this rig is measured against: paired, alternating arms,
# n>=10 requests per arm, 0 garbled.
#
# STRATA_VERIFY_DEVICE_PLAN=0 is already in the shipped config (the device-plan path is
# off on this tree); this script keeps it explicit so the arm is self-describing.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE=strata-swift-iq3_xxs-2gpu-clean
PORT=8081
export BASE PORT
exec "$ROOT/scripts/run-strata.sh" strata-swift-iq3_xxs-2gpu \
    STRATA_VERIFY_DEVICE_PLAN=0
