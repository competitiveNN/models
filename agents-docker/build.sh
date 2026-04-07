#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-agents-cli}"
VERSIONS_FILE="${SCRIPT_DIR}/versions.env"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${CYAN}▸${NC} $*"; }
ok() { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
die() {
	echo -e "${RED}✗${NC} $*" >&2
	exit 1
}

# ── Usage ────────────────────────────────────────────────────────────────────
usage() {
	cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build (or rebuild) the multi-agent CLI Docker image.

Options:
  -n, --name NAME       Image name (default: agents-cli)
  -t, --tag TAG         Extra tag to apply (default: none)
  -f, --force           Build with --no-cache (full rebuild)
      --push            Push the image after building
      --dry-run         Print the build command without running it
      --no-cleanup      Keep old images after building (default: delete old)
  -h, --help            Show this help

Environment variables:
  IMAGE_NAME            Override the image name (default: agents-cli)

Examples:
  $(basename "$0")                          # Build with cache
  $(basename "$0") -f                       # Full rebuild, no cache
  $(basename "$0") -t v2                    # Tag as v2
  $(basename "$0") --push                   # Build and push to registry

Note: Agents are no longer baked into the image. After starting a container,
run setup-agent.sh inside to install agents into the shared volume.
EOF
	exit 0
}

# ── Parse args ───────────────────────────────────────────────────────────────
FORCE=false
DRY_RUN=false
PUSH=false
CLEANUP=true
EXTRA_TAG=""

while [[ $# -gt 0 ]]; do
	case "$1" in
	-n | --name)
		IMAGE_NAME="$2"
		shift 2
		;;
	-t | --tag)
		EXTRA_TAG="$2"
		shift 2
		;;
	-f | --force)
		FORCE=true
		shift
		;;
	--push)
		PUSH=true
		shift
		;;
	--no-cleanup)
		CLEANUP=false
		shift
		;;
	--dry-run)
		DRY_RUN=true
		shift
		;;
	-h | --help) usage ;;
	*) die "Unknown option: $1 (try --help)" ;;
	esac
done

# ── Preflight ────────────────────────────────────────────────────────────────
command -v docker &>/dev/null || die "docker not found in PATH"
[[ -f "$DOCKERFILE" ]] || die "Dockerfile not found at $DOCKERFILE"

# ── Load versions (for reference only — agents are installed at runtime) ─────
if [[ -f "$VERSIONS_FILE" ]]; then
	log "Loading versions from $VERSIONS_FILE (for reference only)"
	# shellcheck source=/dev/null
	source "$VERSIONS_FILE"
else
	warn "No versions.env found"
	CONTAINER_USER=agent
	CONTAINER_UID=$(id -u)
	CONTAINER_GID=$(id -g)
fi

# Set defaults if not already set
CONTAINER_USER="${CONTAINER_USER:-agent}"
CONTAINER_UID="${CONTAINER_UID:-$(id -u)}"
CONTAINER_GID="${CONTAINER_GID:-$(id -g)}"

# ── Generate tags ────────────────────────────────────────────────────────────
TIMESTAMP_TAG="$(date -u +%Y%m%d-%H%M%S)"
DATE_TAG="$(date -u +%Y%m%d)"

# ── Build args ────────────────────────────────────────────────────────────────
BUILD_ARGS=(
	--build-arg "CONTAINER_USER=${CONTAINER_USER}"
	--build-arg "CONTAINER_UID=${CONTAINER_UID}"
	--build-arg "CONTAINER_GID=${CONTAINER_GID}"
	--build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
)

if $FORCE; then
	BUILD_ARGS+=(--no-cache)
	log "Force rebuild (--no-cache)"
fi

# ── Print build summary ─────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}┌──────────────────────────────────────────────────┐${NC}"
echo -e "${CYAN}│        Multi-Agent CLI — Docker Build             │${NC}"
echo -e "${CYAN}├──────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│${NC}  Image:    ${GREEN}${IMAGE_NAME}${NC}"
echo -e "${CYAN}│${NC}  Tags:     ${GREEN}${TIMESTAMP_TAG}, latest${NC}"
[[ -n "$EXTRA_TAG" ]] && echo -e "${CYAN}│${NC}  Extra:    ${GREEN}${EXTRA_TAG}${NC}"
echo -e "${CYAN}│${NC}  Force:    ${FORCE}"
echo -e "${CYAN}│${NC}  Push:     ${PUSH}"
echo -e "${CYAN}│${NC}  Cleanup:  ${CLEANUP}"
echo -e "${CYAN}├──────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│${NC}  Agents are NOT pre-installed."
echo -e "${CYAN}│${NC}  Run setup-agent.sh inside the container to install."
echo -e "${CYAN}└──────────────────────────────────────────────────┘${NC}"
echo ""

# ── Build ────────────────────────────────────────────────────────────────────
DOCKER_CMD=(
	docker build
	"${BUILD_ARGS[@]}"
	-t "${IMAGE_NAME}:${TIMESTAMP_TAG}"
	-t "${IMAGE_NAME}:latest"
	-f "$DOCKERFILE"
	"$SCRIPT_DIR"
)

if $DRY_RUN; then
	log "Dry run — would execute:"
	echo "  ${DOCKER_CMD[*]}"
	exit 0
fi

log "Building image..."

# Stop and remove any existing containers using this image
log "Cleaning up existing containers..."
docker ps -a --filter "ancestor=${IMAGE_NAME}:latest" --format '{{.ID}}' |
	xargs -r docker rm -f 2>/dev/null || true

"${DOCKER_CMD[@]}"

ok "Image built: ${IMAGE_NAME}:${TIMESTAMP_TAG}"

# Apply extra tag if requested
if [[ -n "$EXTRA_TAG" ]]; then
	docker tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${EXTRA_TAG}"
	ok "Tagged: ${IMAGE_NAME}:${EXTRA_TAG}"
fi

# ── Push ─────────────────────────────────────────────────────────────────────
if $PUSH; then
	log "Pushing ${IMAGE_NAME}:latest ..."
	docker push "${IMAGE_NAME}:latest"
	docker push "${IMAGE_NAME}:${TIMESTAMP_TAG}"
	[[ -n "$EXTRA_TAG" ]] && docker push "${IMAGE_NAME}:${EXTRA_TAG}"
	ok "Pushed"
fi

# ── Cleanup old images ───────────────────────────────────────────────────────
if $CLEANUP; then
	log "Cleaning up old images..."
	docker images --filter "reference=${IMAGE_NAME}" --format '{{.ID}} {{.Repository}}:{{.Tag}}' |
		grep -v ":latest$" |
		grep -v ":${TIMESTAMP_TAG}$" |
		grep -v ":${EXTRA_TAG}$" |
		awk '{print $1}' |
		sort -u |
		xargs -r docker rmi -f 2>/dev/null || true
	ok "Cleanup complete"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
ok "Done. Run with persistent volumes:"
echo "  docker run -it -v \$(pwd)/agents-data:/home/agent ${IMAGE_NAME}:latest"
echo ""
ok "The image defines volumes for:"
echo "  - ~/.npm-global (npm packages)"
echo "  - ~/.npm-cache (npm cache)"
echo "  - ~/.local (user data & binaries)"
echo "  - ~/.cache (general cache)"
echo ""
ok "Then run setup-agent.sh inside the container to install agents."
echo "Agents and their data will persist in the mounted volumes."
echo ""
