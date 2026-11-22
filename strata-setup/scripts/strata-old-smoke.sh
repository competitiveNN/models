#!/usr/bin/env bash
# Container smoke test for the built strata-old image.
#
# Verifies the regressions we fixed are still in place, without needing a model:
#   - engine component is installed where the CLI expects it
#   - `strata components engine` reports a usable engine
#   - the level-zero library resolves (no GLIBC_ABI_GNU2_TLS mismatch)
#
# Usage: ./scripts/strata-old-smoke.sh [image]
set -euo pipefail
IMAGE="${1:-localhost/strata-old:latest}"
echo "[smoke] image: $IMAGE"

# 1. engine component present
echo "[smoke] checking engine component placement..."
podman run --rm "$IMAGE" sh -c \
  'test -d /root/.local/share/strata/components/engine && test -f /root/.local/share/strata/components/engine/*/BUILD.json && echo OK' \
  || { echo "[smoke] FAIL: engine component missing"; exit 1; }

# 2. strata reports a usable engine
echo "[smoke] checking strata components engine..."
podman run --rm "$IMAGE" sh -c \
  '/opt/strata/terminal/bin/strata components engine --output json 2>/dev/null | grep -q "\"usable\": *true"' \
  || { echo "[smoke] FAIL: no usable engine reported"; exit 1; }

# 3. level-zero resolves without glibc mismatch (run the engine binary's ldd)
echo "[smoke] checking level-zero / glibc resolution..."
podman run --rm "$IMAGE" sh -c \
  'ldd /root/.local/share/strata/components/engine/*/strata 2>&1 | grep -q "libze_loader.so.1 =>" && ! ldd /root/.local/share/strata/components/engine/*/strata 2>&1 | grep -q "not found"' \
  || { echo "[smoke] FAIL: libze_loader not resolved"; exit 1; }

echo "[smoke] all checks passed."
