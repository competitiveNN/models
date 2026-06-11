#!/usr/bin/env bash
set -euo pipefail

# ── setup-agent.sh: install and configure a specific agent inside the container
#
# Usage:
#   setup-agent.sh opencode [VERSION]
#   setup-agent.sh soulforge [VERSION]
#   setup-agent.sh all     — install every supported agent
#
# Agents are installed into ~/.npm-global (npm agents) or ~/.local/bin (rtk,
# opencode) so they live on the same volume that holds the config files
# (agents-cli-config-local → ~/.local).

# ── Colours ──────────────────────────────────────────────────────────────────
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

# ── Paths ────────────────────────────────────────────────────────────────────
# All agent data goes to persistent volume under $CONTAINER_HOME
CONTAINER_HOME="${HOME:-/home/agent}"
# Ensure base directory exists
mkdir -p "${CONTAINER_HOME}"
NPM_BIN="${CONTAINER_HOME}/.npm-global/bin"
LOCAL_BIN="${CONTAINER_HOME}/.local/bin"
export PATH="${NPM_BIN}:${LOCAL_BIN}:${PATH}"

# Persistent storage directories for agents
PERSISTENT_NPM="${CONTAINER_HOME}/.npm-global"
PERSISTENT_NODE_CACHE="${CONTAINER_HOME}/.npm-cache"
PERSISTENT_LOCAL="${CONTAINER_HOME}/.local"
PERSISTENT_CACHE="${CONTAINER_HOME}/.cache"
PERSISTENT_SHARE="${CONTAINER_HOME}/.local/share"

# ── Ensure directories exist ─────────────────────────────────────────────────
mkdir -p "${NPM_BIN}" "${LOCAL_BIN}" "${PERSISTENT_NPM}" "${PERSISTENT_NODE_CACHE}" "${PERSISTENT_LOCAL}/bin" "${PERSISTENT_CACHE}" "${PERSISTENT_SHARE}"

# ── Agent installers ─────────────────────────────────────────────────────────



install_opencode() {
	local version="${1:-latest}"
	log "Installing OpenCode AI (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" opencode-ai
	else
		npm install --prefix "${PERSISTENT_NPM}" "opencode-ai@${version}"
	fi
	# Create wrapper script for opencode
	mkdir -p "${LOCAL_BIN}"
	cat >"${LOCAL_BIN}/opencode" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/opencode-ai/bin/opencode.exe" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/opencode"
	ok "OpenCode installed: $(${LOCAL_BIN}/opencode --version 2>&1 | head -1)"
	init_rtk --opencode --auto-patch
}

install_pi() {
	local version="${1:-latest}"
	log "Installing Pi agent (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" @earendil-works/pi-coding-agent
	else
		npm install --prefix "${PERSISTENT_NPM}" "@earendil-works/pi-coding-agent@${version}"
	fi
	mkdir -p "${LOCAL_BIN}"
	cat >"${LOCAL_BIN}/pi" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/@earendil-works/pi-coding-agent/bin/pi-cli.js" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/pi"
	ok "Pi installed: $(${LOCAL_BIN}/pi --version 2>&1 | head -1)"
}

install_little_coder() {
	local version="${1:-latest}"
	log "Installing little-coder (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" little-coder
	else
		npm install --prefix "${PERSISTENT_NPM}" "little-coder@${version}"
	fi
	mkdir -p "${LOCAL_BIN}"
	cat >"${LOCAL_BIN}/little-coder" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/little-coder/bin/little-coder.mjs" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/little-coder"

# Ensure pi-coding-agent is reachable for little-coder CLI (workaround for npm flattening)
NESTED_PKG_JSON="${PERSISTENT_NPM}/node_modules/little-coder/node_modules/@earendil-works/pi-coding-agent/package.json"
SCOPED_PKG_DIR="${PERSISTENT_NPM}/node_modules/@earendil-works/pi-coding-agent"
TARGET_PARENT_DIR="${PERSISTENT_NPM}/node_modules/little-coder/node_modules/@earendil-works"

if [[ ! -f "${NESTED_PKG_JSON}" ]]; then
  warn "pi-coding-agent not found inside little-coder; installing scoped package and creating symlink"
  npm install --prefix "${PERSISTENT_NPM}" @earendil-works/pi-coding-agent || warn "Failed to install @earendil-works/pi-coding-agent"
  mkdir -p "${TARGET_PARENT_DIR}"
  if [[ -d "${SCOPED_PKG_DIR}" ]]; then
    ln -sf "${SCOPED_PKG_DIR}" "${TARGET_PARENT_DIR}/pi-coding-agent"
    ok "Linked @earendil-works/pi-coding-agent into little-coder node_modules"
  else
    warn "Scoped package not found at ${SCOPED_PKG_DIR}; little-coder may still fail"
  fi
fi

ok "little-coder installed: $(${LOCAL_BIN}/little-coder --version 2>&1 | head -1)"
}


install_openlumara() {
	local version="${1:-main}"
	log "Installing OpenLumara (branch/tag: ${version})..."
	local OPENLUMARA_CODE="${PERSISTENT_SHARE}/openlumara"
	mkdir -p "${PERSISTENT_SHARE}"
	if [[ -d "${OPENLUMARA_CODE}/.git" ]]; then
		warn "OpenLumara source already exists at ${OPENLUMARA_CODE}, pulling latest..."
		git -C "${OPENLUMARA_CODE}" pull origin "$version" || true
	else
		git clone --branch "$version" \
			https://github.com/Rose22/openlumara.git "${OPENLUMARA_CODE}"
	fi
	mkdir -p "${LOCAL_BIN}"
	cat >"${LOCAL_BIN}/openlumara" <<EOF
#!/usr/bin/env bash
cd "${OPENLUMARA_CODE}" && exec bash ./run.sh "\$@"
EOF
	chmod +x "${LOCAL_BIN}/openlumara"
	ok "OpenLumara installed"
}



install_soulforge() {
	local version="${1:-latest}"
	log "Installing SoulForge Agent (${version})..."

	# Create soulforge directories in persistent volume
	mkdir -p "${PERSISTENT_SHARE}/soulforge" "${PERSISTENT_CACHE}/soulforge"

	# Create temp directory for download
	local TMP_DIR
	TMP_DIR=$(mktemp -d)
	local SOULFORGE_TAR=""

	# Detect platform
	local platform=""
	if [[ "$(uname -s)" == "Linux" ]]; then
		platform="linux"
	elif [[ "$(uname -s)" == "Darwin" ]]; then
		platform="macos"
	else
		warn "Unsupported platform: $(uname -s)"
		return 1
	fi

	local arch=""
	case "$(uname -m)" in
	x86_64) arch="x64" ;;
	aarch64) arch="arm64" ;;
	armv7l) arch="armv7" ;;
	*)
		warn "Unsupported architecture: $(uname -m)"
		return 1
		;;
	esac

	# Download latest release
	log "Downloading SoulForge prebuilt binary..."
	local download_url=""
	local tar_name=""

	# Try to get the latest release info
	if command -v curl &>/dev/null && command -v jq &>/dev/null; then
		local api_url="https://api.github.com/repos/ProxySoul/soulforge/releases/latest"
		local release_info
		release_info=$(curl -s "$api_url" 2>/dev/null)

		if [[ $? -eq 0 && -n "$release_info" ]]; then
			# Find the appropriate asset for this platform
			local asset_url=""
			asset_url=$(echo "$release_info" | jq -r ".assets[] | select(.name | contains(\"${platform}\") and contains(\"${arch}\")) | .browser_download_url" | head -1)

			if [[ -n "$asset_url" && "$asset_url" != "null" ]]; then
				download_url="$asset_url"
				tar_name=$(basename "$asset_url")
			fi
		fi
	fi

	# Fallback to manual URL construction if API fails
	if [[ -z "$download_url" ]]; then
		warn "Could not fetch release info via API, trying direct download..."
		# This is a fallback - in practice you'd want to use a known version
		download_url="https://github.com/ProxySoul/soulforge/releases/download/v2.7.0/soulforge-v2.7.0-${platform}-${arch}.tar.gz"
		tar_name="soulforge-v2.7.0-${platform}-${arch}.tar.gz"
	fi

	log "Downloading from: $download_url"
	if ! curl -fsSL "$download_url" -o "${TMP_DIR}/${tar_name}" 2>/dev/null; then
		warn "Download failed for ${tar_name}"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# Extract
	log "Extracting..."
	cd "$TMP_DIR"
	if ! tar xzf "${tar_name}"; then
		warn "Extraction failed"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# Find extracted directory
	local extracted_dir=""
	extracted_dir=$(find . -maxdepth 1 -type d -name "soulforge*" | head -1)

	if [[ -z "$extracted_dir" ]]; then
		warn "Could not find extracted directory"
		rm -rf "$TMP_DIR"
		return 1
	fi

	cd "$extracted_dir"

	# Run install script
	if [[ -f "./install.sh" ]]; then
		log "Running install script..."
		if bash ./install.sh; then
			log "SoulForge installed successfully via prebuilt binary"
		else
			warn "Install script failed"
			rm -rf "$TMP_DIR"
			return 1
		fi
	else
		warn "Install script not found in extracted package"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# Clean up
	rm -rf "$TMP_DIR"

	# Find and link the binary
	local soulforge_path=""
	# Wait a moment for installation to complete
	sleep 2
	# Search for the binary in multiple possible locations
	soulforge_path=$(find "${CONTAINER_HOME}/.soulforge" "${CONTAINER_HOME}/.local/share/soulforge" -name "soulforge" -type f -executable 2>/dev/null | head -1)

	if [[ -n "$soulforge_path" && -x "$soulforge_path" ]]; then
		mkdir -p "${LOCAL_BIN}"
		ln -sf "$soulforge_path" "${LOCAL_BIN}/soulforge" 2>/dev/null || true
		ok "SoulForge installed: $(${LOCAL_BIN}/soulforge --version 2>&1 | head -1)"
	else
		warn "Could not locate SoulForge binary after installation"
		# Debug: show what we found
		find "${CONTAINER_HOME}/.soulforge" "${CONTAINER_HOME}/.local/share/soulforge" -name "*soulforge*" 2>/dev/null || true
	fi
}

init_rtk() {
	if command -v rtk &>/dev/null; then
		log "Initializing RTK $*..."
		rtk init -g "$@" 2>/dev/null || warn "rtk init failed (may already be initialised)"
	else
		warn "rtk not found — skipping RTK initialisation"
	fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

usage() {
	cat <<EOF
Usage: setup-agent.sh <agent> [version]

Agents:
  opencode     OpenCode AI
  openlumara   OpenLumara Agent (Python)
  pi           Pi coding agent (TypeScript)
  little-coder little-coder coding agent (TypeScript)
  soulforge    SoulForge Agent (TypeScript/Bun)
  all          Install every supported agent

Examples:
  setup-agent.sh openlumara main
  setup-agent.sh pi latest
  setup-agent.sh little-coder latest
  setup-agent.sh soulforge
  setup-agent.sh all
EOF
	exit 0
}

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
	usage
fi

AGENT="${1,,}"

VERSION="${2:-latest}"

case "$AGENT" in
opencode) install_opencode "$VERSION" ;;
openlumara) install_openlumara "$VERSION" ;;
pi) install_pi "$VERSION" ;;
little-coder) install_little_coder "$VERSION" ;;
soulforge) install_soulforge "$VERSION" ;;
watchdog) install_watchdog ;;
all)
	log "Installing all agents..."
	install_opencode "$VERSION"
	install_openlumara "$VERSION"
	install_pi "$VERSION"
	install_little_coder "$VERSION"
	install_soulforge "$VERSION"
	ok "All agents installed"
	;;
*) die "Unknown agent: $AGENT (run setup-agent.sh --help for usage)" ;;
esac
