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
  -u, --update AGENT    Force-rebuild a single agent layer
                         (copilot | gemini | opencode | qwen | kilo | hermes)
      --push            Push the image after building
      --dry-run         Print the build command without running it
      --no-cleanup      Keep old images after building (default: delete old)
  -h, --help            Show this help

Environment variables:
  IMAGE_NAME            Override the image name (default: agents-cli)

Examples:
  $(basename "$0")                          # Build with cache
  $(basename "$0") -f                       # Full rebuild, no cache
  $(basename "$0") -u gemini                # Rebuild only the gemini layer
  $(basename "$0") -t v2 -u kilo -u hermes  # Tag as v2, rebuild kilo+hermes
  $(basename "$0") --push                   # Build and push to registry
EOF
	exit 0
}

# ── Parse args ───────────────────────────────────────────────────────────────
FORCE=false
DRY_RUN=false
PUSH=false
CLEANUP=true
EXTRA_TAG=""
BUILD_AGENTS=()

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
	-u | --update)
		BUILD_AGENTS+=("$2")
		shift 2
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

# ── Load versions ────────────────────────────────────────────────────────────
if [[ -f "$VERSIONS_FILE" ]]; then
	log "Loading versions from $VERSIONS_FILE"
	# shellcheck source=/dev/null
	source "$VERSIONS_FILE"
else
	warn "No versions.env found — using 'latest' for all agents"
	COPILOT_VERSION=latest
	GEMINI_CLI_VERSION=latest
	OPENCODE_AI_VERSION=latest
	QWEN_CODE_VERSION=latest
	KILO_CLI_VERSION=latest
	HERMES_AGENT_BRANCH=main
	CONTAINER_USER=agent
	CONTAINER_UID=1001
	CONTAINER_GID=1001
fi

# Set defaults if not already set
CONTAINER_USER="${CONTAINER_USER:-agent}"
CONTAINER_UID="${CONTAINER_UID:-1001}"
CONTAINER_GID="${CONTAINER_GID:-1001}"

# ── Generate tags ────────────────────────────────────────────────────────────
TIMESTAMP_TAG="$(date -u +%Y%m%d-%H%M%S)"
DATE_TAG="$(date -u +%Y%m%d)"

# ── Build args ────────────────────────────────────────────────────────────────
BUILD_ARGS=(
	--build-arg "COPILOT_VERSION=${COPILOT_VERSION:-latest}"
	--build-arg "GEMINI_CLI_VERSION=${GEMINI_CLI_VERSION:-latest}"
	--build-arg "OPENCODE_AI_VERSION=${OPENCODE_AI_VERSION:-latest}"
	--build-arg "QWEN_CODE_VERSION=${QWEN_CODE_VERSION:-latest}"
	--build-arg "KILO_CLI_VERSION=${KILO_CLI_VERSION:-latest}"
	--build-arg "HERMES_AGENT_BRANCH=${HERMES_AGENT_BRANCH:-main}"
	--build-arg "CONTAINER_USER=${CONTAINER_USER}"
	--build-arg "CONTAINER_UID=${CONTAINER_UID}"
	--build-arg "CONTAINER_GID=${CONTAINER_GID}"
	--build-arg "BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
)

# ── Cache busting for targeted agent updates ─────────────────────────────────
# Docker caches layers by their instruction. To force-rebuild from a specific
# layer onward we inject a unique bust arg that changes the FROM or first
# agent layer. This is a pragmatic approach — for full control use --force.
if [[ ${#BUILD_AGENTS[@]} -gt 0 ]]; then
	log "Forcing rebuild of: ${BUILD_AGENTS[*]}"
	BUST_KEY="$(
		IFS=,
		echo "${BUILD_AGENTS[*]}"
	)-$(date +%s)"
	BUILD_ARGS+=(--build-arg "CACHE_BUST=${BUST_KEY}")
	# Insert a CACHE_BUST ARG in the Dockerfile context — we pass it as
	# a build-arg. The Dockerfile doesn't USE it, but any layer after the
	# first changed build-arg won't match cache. To target specific agents
	# we rebuild from scratch for those agents. In practice, use --force
	# for a clean rebuild or rely on the fact that changing a build-arg
	# invalidates all subsequent layers.
	FORCE=true
	warn "Targeted update forces --no-cache for layers after the changed agent."
fi

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
echo -e "${CYAN}│${NC}  copilot   = ${COPILOT_VERSION:-latest}"
echo -e "${CYAN}│${NC}  gemini    = ${GEMINI_CLI_VERSION:-latest}"
echo -e "${CYAN}│${NC}  opencode  = ${OPENCODE_AI_VERSION:-latest}"
echo -e "${CYAN}│${NC}  qwen      = ${QWEN_CODE_VERSION:-latest}"
echo -e "${CYAN}│${NC}  kilo      = ${KILO_CLI_VERSION:-latest}"
echo -e "${CYAN}│${NC}  hermes    = ${HERMES_AGENT_BRANCH:-main} (branch)"
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
	docker images --format '{{.Repository}}:{{.Tag}}' "${IMAGE_NAME}" |
		grep -v ":latest" |
		grep -v ":${TIMESTAMP_TAG}" |
		grep -v ":${EXTRA_TAG}" |
		xargs -r docker rmi || true
	ok "Cleanup complete"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
ok "Done. Run with:  docker run -it ${IMAGE_NAME}:latest"
echo ""
