#!/usr/bin/env bash
set -euo pipefail

# Wrapper for `pi install <extension>` that copies the installed extension
# into little-coder's .pi/extensions directory so little-coder can use it.
# Usage: pi-install-wrapper.sh <extension> [<extension>...]

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
log(){ printf "${CYAN}▸${NC} %s\n" "$*"; }
ok(){ printf "${GREEN}✓${NC} %s\n" "$*"; }
warn(){ printf "${YELLOW}⚠${NC} %s\n" "$*"; }

if ! command -v pi >/dev/null 2>&1; then
  warn "pi CLI not found in PATH"
  exit 1
fi

CONTAINER_HOME="${HOME:-/home/agent}"
NPM_GLOBAL="${CONTAINER_HOME}/.npm-global"

get_little_coder_extensions_dir(){
  local candidates=(
    "${NPM_GLOBAL}/lib/node_modules/little-coder/.pi/extensions"
    "${NPM_GLOBAL}/node_modules/little-coder/.pi/extensions"
  )
  if command -v npm >/dev/null 2>&1; then
    local npm_root
    npm_root=$(npm root -g 2>/dev/null || true)
    if [[ -n "${npm_root}" ]]; then
      candidates+=("${npm_root}/little-coder/.pi/extensions")
    fi
  fi
  candidates+=("/usr/local/lib/node_modules/little-coder/.pi/extensions" "/usr/lib/node_modules/little-coder/.pi/extensions")

  for c in "${candidates[@]}"; do
    local pkg_dir="${c%/.pi/extensions}"
    if [[ -d "${pkg_dir}" ]]; then
      echo "${c}"
      return 0
    fi
  done

  # fallback (create under default prefix)
  echo "${candidates[0]}"
}

DEST_ROOT=$(get_little_coder_extensions_dir)
mkdir -p "${DEST_ROOT}" || true

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <extension> [<extension>...]" >&2
  exit 1
fi

for ext in "$@"; do
  log "Installing PI extension: ${ext}"
  if ! pi install "${ext}"; then
    warn "pi install failed for ${ext}"
    continue
  fi

  # Common install location for pi agent npm packages
  src="${CONTAINER_HOME}/.pi/agent/npm/node_modules/${ext}"
  if [[ ! -d "${src}" ]]; then
    # try to find exact path under ~/.pi
    src=$(find "${CONTAINER_HOME}/.pi" -type d -path "*/node_modules/${ext}" -print -quit 2>/dev/null || true)
  fi
  if [[ -z "${src}" || ! -d "${src}" ]]; then
    # last-resort: find by basename
    bn=$(basename "${ext}")
    src=$(find "${CONTAINER_HOME}/.pi" -type d -name "${bn}" -path "*/node_modules/*" -print -quit 2>/dev/null || true)
  fi

  if [[ -z "${src}" || ! -d "${src}" ]]; then
    warn "Could not locate installed extension directory for ${ext}; skipping copy"
    continue
  fi

  dest="${DEST_ROOT}/${ext}"
  mkdir -p "$(dirname "${dest}")"
  rm -rf "${dest}" || true
  log "Copying ${src} -> ${dest}"
  cp -a "${src}" "${dest}"
  ok "Copied ${ext} -> ${dest}"
done

exit 0
