#!/usr/bin/env bash
set -euo pipefail

# ── cleanup-volumes.sh: remove all Docker volumes used by agents-cli ────────
# This script removes all volumes created by agents-cli to free up disk space.
# WARNING: This will permanently delete all agent configurations and data!

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_VOLUME="${AGENTS_VOLUME:-agents-cli-config}"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}▸${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
error() { echo -e "${RED}✗${NC} $*" >&2; }
ok() { echo -e "${GREEN}✓${NC} $*"; }

# ── Safety check ─────────────────────────────────────────────────────────────
if [[ "${1:-}" != "--confirm" ]]; then
	echo ""
	echo -e "${RED}WARNING: This will permanently delete all agent configurations and data!${NC}"
	echo ""
	echo "This script will remove the following Docker volumes:"
	echo "  - ${AGENTS_VOLUME} (agent configs)"
	echo "  - ${AGENTS_VOLUME}-copilot (Copilot configs)"
	echo "  - ${AGENTS_VOLUME}-hermes (Hermes configs)"
	echo "  - ${AGENTS_VOLUME}-local (local data & binaries)"
	echo "  - ${AGENTS_VOLUME}-npm-global (npm packages)"
	echo "  - ${AGENTS_VOLUME}-npm-cache (npm cache)"
	echo "  - ${AGENTS_VOLUME}-cache (general cache)"
	echo ""
	echo "Run with --confirm to proceed:"
	echo "  $0 --confirm"
	echo ""
	exit 1
fi

# ── Stop any running containers ──────────────────────────────────────────────
log "Stopping any running agents-cli containers..."
docker ps -q --filter "ancestor=agents-cli:latest" | xargs -r docker stop || true
docker ps -a -q --filter "ancestor=agents-cli:latest" | xargs -r docker rm || true

# ── Remove volumes ───────────────────────────────────────────────────────────
VOLUMES=(
	"${AGENTS_VOLUME}"
	"${AGENTS_VOLUME}-copilot"
	"${AGENTS_VOLUME}-hermes"
	"${AGENTS_VOLUME}-local"
	"${AGENTS_VOLUME}-npm-global"
	"${AGENTS_VOLUME}-npm-cache"
	"${AGENTS_VOLUME}-cache"
)

log "Removing Docker volumes..."
for vol in "${VOLUMES[@]}"; do
	if docker volume inspect "$vol" &>/dev/null; then
		log "Removing volume: $vol"
		docker volume rm "$vol" || warn "Failed to remove volume: $vol"
	else
		log "Volume not found: $vol"
	fi
done

# ── Clean up dangling resources ──────────────────────────────────────────────
log "Cleaning up dangling Docker resources..."
docker system prune -f >/dev/null 2>&1 || true

ok "Cleanup complete!"
ok "All agent volumes have been removed."
echo ""
warn "Note: If you were using bind mounts (-v /host/path:/container/path),"
warn "those host directories are not affected by this cleanup."
