#!/usr/bin/env bash
set -euo pipefail

# ── setup-agent.sh: install and configure a specific agent inside the container
#
# Usage:
#   setup-agent.sh copilot [VERSION]
#   setup-agent.sh gemini  [VERSION]
#   setup-agent.sh opencode [VERSION]
#   setup-agent.sh qwen    [VERSION]
#   setup-agent.sh kilo    [VERSION]
#   setup-agent.sh hermes  [BRANCH]
#   setup-agent.sh soulforge [VERSION]
#   setup-agent.sh all     — install every supported agent
#
# Agents are installed into ~/.npm-global (npm agents) or ~/.local/bin (rtk,
# hermes) so they live on the same volume that holds the config files
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

# Link soulforge data to persistent volume
mkdir -p "${PERSISTENT_SHARE}/soulforge" "${PERSISTENT_CACHE}/soulforge"
ln -sf "${PERSISTENT_SHARE}/soulforge" "${CONTAINER_HOME}/.soulforge" 2>/dev/null || true

# ── Agent installers ─────────────────────────────────────────────────────────

install_copilot() {
	local version="${1:-latest}"
	log "Installing GitHub Copilot CLI (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" @github/copilot
	else
		npm install --prefix "${PERSISTENT_NPM}" "@github/copilot@${version}"
	fi
	# Create wrapper script for copilot
	mkdir -p "${LOCAL_BIN}"
	cat > "${LOCAL_BIN}/copilot" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/@github/copilot/npm-loader.js" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/copilot"
	ok "Copilot installed: $(${LOCAL_BIN}/copilot --version 2>&1 | head -1)"
	init_rtk --auto-patch
}

install_gemini() {
	local version="${1:-latest}"
	log "Installing Google Gemini CLI (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" @google/gemini-cli
	else
		npm install --prefix "${PERSISTENT_NPM}" "@google/gemini-cli@${version}"
	fi
	# Create wrapper script for gemini
	mkdir -p "${LOCAL_BIN}"
	cat > "${LOCAL_BIN}/gemini" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/@google/gemini-cli/bundle/gemini.js" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/gemini"
	ok "Gemini installed: $(${LOCAL_BIN}/gemini --version 2>&1 | head -1)"
	init_rtk --gemini --auto-patch
}

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
	cat > "${LOCAL_BIN}/opencode" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/opencode-ai/bin/opencode" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/opencode"
	ok "OpenCode installed: $(${LOCAL_BIN}/opencode --version 2>&1 | head -1)"
	init_rtk --opencode --auto-patch
}

install_qwen() {
	local version="${1:-latest}"
	log "Installing Qwen Code (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" @qwen-code/qwen-code
	else
		npm install --prefix "${PERSISTENT_NPM}" "@qwen-code/qwen-code@${version}"
	fi
	# Create wrapper script for qwen
	cat > "${LOCAL_BIN}/qwen" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/@qwen-code/qwen-code/cli.js" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/qwen"
	ok "Qwen installed: $(${LOCAL_BIN}/qwen --version 2>&1 | head -1)"
}

install_kilo() {
	local version="${1:-latest}"
	log "Installing Kilo CLI (${version})..."
	if [[ "$version" == "latest" ]]; then
		npm install --prefix "${PERSISTENT_NPM}" @kilocode/cli
	else
		npm install --prefix "${PERSISTENT_NPM}" "@kilocode/cli@${version}"
	fi
	# Create wrapper script for kilo
	mkdir -p "${LOCAL_BIN}"
	cat > "${LOCAL_BIN}/kilo" <<EOF
#!/usr/bin/env bash
NPM_PREFIX="${PERSISTENT_NPM}" exec "\$NPM_PREFIX/node_modules/@kilocode/cli/bin/kilo" "\$@"
EOF
	chmod +x "${LOCAL_BIN}/kilo"
	ok "Kilo installed: $(${LOCAL_BIN}/kilo --version 2>&1 | head -1)"
}

install_hermes() {
	local branch="${1:-main}"
	log "Installing Hermes Agent (branch: ${branch})..."

	# Use the official hermes installation script
	if curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --no-venv --skip-setup --dir "${PERSISTENT_SHARE}/hermes-agent"; then
		log "Hermes installation completed successfully"
	else
		warn "Hermes installation script failed, trying fallback method..."

		# Fallback: manual installation if the official script fails
		local HERMES_CODE="${PERSISTENT_SHARE}/hermes-agent"
		mkdir -p "${HERMES_CODE}"

		if [[ -d "${HERMES_CODE}/.git" ]]; then
			warn "Hermes source already exists at ${HERMES_CODE}, pulling latest..."
			git -C "${HERMES_CODE}" pull origin "$branch" || true
		else
			git clone --branch "$branch" \
				https://github.com/NousResearch/hermes-agent.git "${HERMES_CODE}"
		fi

		# Copy the hermes script to our bin directory
		mkdir -p "${LOCAL_BIN}"
		cp "${HERMES_CODE}/hermes" "${LOCAL_BIN}/hermes"
		chmod +x "${LOCAL_BIN}/hermes"

		# Modify the Python script to add the source directory to sys.path
		sed -i '1a import sys; sys.path.insert(0, "'${HERMES_CODE}'")' "${LOCAL_BIN}/hermes"
	fi

	ok "Hermes installed: $(${LOCAL_BIN}/hermes --version 2>&1 | head -1 || echo 'Installed')"
}

install_soulforge() {
	local version="${1:-latest}"
	log "Installing SoulForge Agent (${version})..."

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
		x86_64)  arch="x64" ;;
		aarch64) arch="arm64" ;;
		armv7l) arch="armv7" ;;
		*)
			warn "Unsupported architecture: $(uname -m)"
			return 1
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
  copilot     GitHub Copilot CLI
  gemini      Google Gemini CLI
  opencode    OpenCode AI
  qwen        Qwen Code
  kilo        Kilo CLI
  hermes      Hermes Agent (Python)
  soulforge   SoulForge Agent (TypeScript/Bun)
  all         Install every supported agent

Examples:
  setup-agent.sh copilot
  setup-agent.sh gemini 0.12.0
  setup-agent.sh hermes main
  setup-agent.sh soulforge
  setup-agent.sh all
EOF
	exit 0
}

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
	usage
fi

AGENT="${1,,}"

# Set appropriate default version/branch based on agent type
if [[ "$AGENT" == "hermes" ]]; then
	VERSION="${2:-main}"
else
	VERSION="${2:-latest}"
fi

case "$AGENT" in
copilot) install_copilot "$VERSION" ;;
gemini) install_gemini "$VERSION" ;;
opencode) install_opencode "$VERSION" ;;
qwen) install_qwen "$VERSION" ;;
kilo) install_kilo "$VERSION" ;;
hermes) install_hermes "$VERSION" ;;
soulforge) install_soulforge "$VERSION" ;;
all)
	log "Installing all agents..."
	install_copilot "$VERSION"
	install_gemini "$VERSION"
	install_opencode "$VERSION"
	install_qwen "$VERSION"
	install_kilo "$VERSION"
	install_hermes "$VERSION"
	install_soulforge "$VERSION"
	ok "All agents installed"
	;;
*) die "Unknown agent: $AGENT (run setup-agent.sh --help for usage)" ;;
esac
