#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

RENDER_GID="$(getent group render | cut -d: -f3 2>/dev/null || id -u)"
export RENDER_GID
export MODELS_DIR="${MODELS_DIR:-/var/home/fra/data/models/safetensors}"

if [ ! -d "$MODELS_DIR" ]; then
  echo "MODELS_DIR does not exist: $MODELS_DIR" >&2
  exit 1
fi

echo "==> Building grimoire-b580 image (this may take ~30-60 minutes on first build)"
docker compose build

echo "==> Quick sanity check: Qwen generate on gpu0"
docker compose run --rm qwen-generate

echo "==> Done. Start the server: docker compose up -d qwen27b or ornith35b"
echo "==> OpenAI-compatible at: http://localhost:8027 (Qwen) / http://localhost:8035 (Ornith)"
