#!/bin/sh
# Isolate the token-count effect: run the SAME prompt at 20/60/120/200 tokens,
# each on a FRESH engine, with DEVICE_PLAN=0.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROMPT="Tell me a story about a robot learning to paint, with dialogue."
for MT in 20 60 120 200; do
    echo "========== max_tokens=$MT =========="
    PORT=8081 timeout 700 "$ROOT/one-req.sh" tc-$MT "STRATA_VERIFY_DEVICE_PLAN=0" "$MT" <<EOF
$PROMPT
EOF
    echo
done
echo "========== ALL DONE =========="