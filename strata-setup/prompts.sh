#!/bin/sh
# Test each trial prompt in ISOLATION on a fresh engine with DEVICE_PLAN=0.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
P1="Say hello in one short sentence."
P2="Write a haiku about the sea."
P3="Explain what a transformer is, in two paragraphs."
P4="Tell me a story about a robot learning to paint, with dialogue."
i=1
for pair in "20:$P1" "60:$P2" "120:$P3" "200:$P4"; do
    MT="${pair%%:*}"; P="${pair#*:}"
    echo "========== req$((i++)) max_tokens=$MT =========="
    PORT=8081 "$ROOT/one-req-prompt.sh" p$i "STRATA_VERIFY_DEVICE_PLAN=0" "$MT" "$P"
    echo
done
echo "========== ALL DONE =========="