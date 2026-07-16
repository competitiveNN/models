#!/usr/bin/env bash
set -euo pipefail

# ── setup-agent.sh: install and configure a specific agent inside the container
#
# Usage:
#   setup-agent.sh empryo [VERSION]
#   setup-agent.sh all     — install every supported agent
#
# Agents are installed into ~/.npm-global (npm agents) or ~/.local/bin (rtk)
# so they live on the same volume that holds the config files
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




# User packages:
#   npm:pi-subagents
#     /home/agent/.pi/agent/npm/node_modules/pi-subagents
#   npm:@juicesharp/rpiv-ask-user-question
#     /home/agent/.pi/agent/npm/node_modules/@juicesharp/rpiv-ask-user-question
#   npm:pi-tokensaver
#     /home/agent/.pi/agent/npm/node_modules/pi-tokensaver
#   npm:@hypabolic/pi-hypa
#     /home/agent/.pi/agent/npm/node_modules/@hypabolic/pi-hypa
#   npm:context-mode
#     /home/agent/.pi/agent/npm/node_modules/context-mode
#   npm:@juicesharp/rpiv-todo
#     /home/agent/.pi/agent/npm/node_modules/@juicesharp/rpiv-todo
#   npm:@ayulab/pi-rewind
#     /home/agent/.pi/agent/npm/node_modules/@ayulab/pi-rewind
#   npm:pi-lens
#     /home/agent/.pi/agent/npm/node_modules/pi-lens
#   npm:@plannotator/pi-extension
#     /home/agent/.pi/agent/npm/node_modules/@plannotator/pi-extension
#   npm:@ff-labs/pi-fff
#     /home/agent/.pi/agent/npm/node_modules/@ff-labs/pi-fff
#   npm:@narumitw/pi-goal
#     /home/agent/.pi/agent/npm/node_modules/@narumitw/pi-goal
#   npm:gentle-engram@0.1.8
#     /home/agent/.pi/agent/npm/node_modules/gentle-engram
#   npm:pi-mcp-adapter
#     /home/agent/.pi/agent/npm/node_modules/pi-mcp-adapter
#   npm:@juicesharp/rpiv-web-tools
#     /home/agent/.pi/agent/npm/node_modules/@juicesharp/rpiv-web-tools
#   npm:npm:pi-lens
#     /home/agent/.pi/agent/npm/node_modules/@apmantza/pi-lens
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

	# Recreate persistent directory symlink
	mkdir -p "${CONTAINER_HOME}/.config/pi"
	ln -sfn "${CONTAINER_HOME}/.config/pi" "${CONTAINER_HOME}/.pi" 2>/dev/null || true

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
cat >"${LOCAL_BIN}/little-coder" <<'LC_WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

NPM_PREFIX="__PERSISTENT_NPM__"
EXT_REGISTRY="__PERSISTENT_NPM__/.little-coder-extensions"

# Build list of existing -e extension args provided by user
existing_exts=()
args=( "$@" )
i=0
while [ $i -lt ${#args[@]} ]; do
  a="${args[$i]}"
  if [ "$a" = "-e" ]; then
    next=$((i+1))
    if [ $next -lt ${#args[@]} ]; then
      existing_exts+=( "${args[$next]}" )
      i=$((i+2))
      continue
    fi
  elif [[ "$a" == -e* && "$a" != "-e" ]]; then
    # combined form like -enpm:foo
    existing_exts+=( "${a#-e}" )
  fi
  i=$((i+1))
done

append_args=()
if [ -f "$EXT_REGISTRY" ]; then
  while IFS= read -r ext; do
    # trim whitespace
    trimmed="$(echo "$ext" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [ -z "$trimmed" ] && continue
    case "$trimmed" in \#*) continue ;; esac
    skip=false
    for e in "${existing_exts[@]}"; do
      if [ "$e" = "$trimmed" ]; then skip=true; break; fi
    done
    if ! $skip; then
      append_args+=( "-e" "$trimmed" )
    fi
  done < "$EXT_REGISTRY"
fi

exec "$NPM_PREFIX/node_modules/little-coder/bin/little-coder.mjs" "$@" "${append_args[@]}"
LC_WRAPPER
# replace placeholder with actual path
sed -i "s|__PERSISTENT_NPM__|${PERSISTENT_NPM}|g" "${LOCAL_BIN}/little-coder"
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





install_empryo() {
	local version="${1:-latest}"
	log "Installing Empryo Agent (${version})..."

	# Empryo installs everything into ~/.empryo/ (binary, native libs, wasm,
	# fonts and config), which sits directly under $HOME and is NOT on a
	# persistent volume. Pre-symlink it to the persistent -local volume so the
	# whole install survives container restarts. The installer hardcodes
	# ~/.empryo as its target, so this must exist before we run it.
	local EMPRYO_BACKING="${PERSISTENT_SHARE}/empryo"
	mkdir -p "${EMPRYO_BACKING}"
	ln -sfn "${EMPRYO_BACKING}" "${CONTAINER_HOME}/.empryo"

	# The official installer verifies a detached RSA signature + SHA256 checksum,
	# which require openssl and sha256sum/shasum to be present.
	if ! command -v openssl >/dev/null 2>&1; then
		warn "openssl is required by the Empryo installer — refusing to install"
		return 1
	fi
	if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
		warn "sha256sum (or shasum) is required by the Empryo installer — refusing to install"
		return 1
	fi

	# Honor an explicit version pin (EMPRYO_VERSION expects x.y.z, no leading v).
	if [[ "$version" != "latest" && -n "$version" ]]; then
		export EMPRYO_VERSION="${version#v}"
	fi
	export EMPRYO_QUIET=1

	log "Running the official installer: curl -fsSL empryo.com/install.sh | bash"
	if ! bash -c 'curl -fsSL https://empryo.com/install.sh | bash'; then
		unset EMPRYO_VERSION EMPRYO_QUIET 2>/dev/null || true
		warn "Empryo install failed"
		return 1
	fi
	unset EMPRYO_VERSION EMPRYO_QUIET 2>/dev/null || true

	# Expose the binary (and its 'em' alias) on PATH via the persistent local bin.
	mkdir -p "${LOCAL_BIN}"
	ln -sf "${CONTAINER_HOME}/.empryo/bin/empryo" "${LOCAL_BIN}/empryo" 2>/dev/null || true
	ln -sf "${CONTAINER_HOME}/.empryo/bin/em" "${LOCAL_BIN}/em" 2>/dev/null || true

	ok "Empryo installed: $(${LOCAL_BIN}/empryo --version 2>&1 | head -1)"
}

install_engram() {
	local version="${1:-latest}"
	log "Installing Engram (${version})..."

	# Detect platform
	local platform=""
	if [[ "$(uname -s)" == "Linux" ]]; then
		platform="linux"
	elif [[ "$(uname -s)" == "Darwin" ]]; then
		platform="darwin"
	else
		warn "Unsupported platform: $(uname -s)"
		return 1
	fi

	local arch=""
	case "$(uname -m)" in
	x86_64) arch="amd64" ;;
	aarch64|arm64) arch="arm64" ;;
	*)
		warn "Unsupported architecture: $(uname -m)"
		return 1
		;;
	esac

	# Create temp directory for download
	local TMP_DIR
	TMP_DIR=$(mktemp -d)
	local download_url=""
	local tar_name=""

	# Try to get release info via API
	if command -v curl &>/dev/null && command -v jq &>/dev/null; then
		local api_url="https://api.github.com/repos/Gentleman-Programming/engram/releases/latest"
		if [[ "$version" != "latest" ]]; then
			api_url="https://api.github.com/repos/Gentleman-Programming/engram/releases/tags/${version}"
		fi
		local release_info
		release_info=$(curl -s "$api_url" 2>/dev/null)

		if [[ $? -eq 0 && -n "$release_info" ]]; then
			# Check if response is an error
			if echo "$release_info" | jq -e '.message' >/dev/null 2>&1; then
				warn "API error: $(echo "$release_info" | jq -r '.message')"
			else
				# Find the asset matching our platform and arch
				local asset_url=""
				asset_url=$(echo "$release_info" | jq -r ".assets[]? | select(.name | contains(\"${platform}\") and contains(\"${arch}\") and endswith(\".tar.gz\")) | .browser_download_url" 2>/dev/null | head -1)

				if [[ -n "$asset_url" && "$asset_url" != "null" ]]; then
					download_url="$asset_url"
					tar_name=$(basename "$asset_url")
				fi
			fi
		fi
	fi

	# Fallback to direct download URL construction if API fails
	if [[ -z "$download_url" ]]; then
		warn "Could not fetch release info via API, trying direct download..."
		local fallback_version="1.17.0"
		if [[ "$version" != "latest" ]]; then
			fallback_version="${version#v}"
		fi
		download_url="https://github.com/Gentleman-Programming/engram/releases/download/v${fallback_version}/engram_${fallback_version}_${platform}_${arch}.tar.gz"
		tar_name="engram_${fallback_version}_${platform}_${arch}.tar.gz"
	fi

	log "Downloading from: $download_url"
	if ! curl -fsSL "$download_url" -o "${TMP_DIR}/${tar_name}"; then
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

	# Find engram binary and move it to LOCAL_BIN
	if [[ -f "engram" ]]; then
		mkdir -p "${LOCAL_BIN}"
		chmod +x engram
		mv engram "${LOCAL_BIN}/engram"
		ok "Engram binary installed successfully to ${LOCAL_BIN}/engram"
	else
		warn "engram binary not found in the extracted archive"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# Clean up
	rm -rf "$TMP_DIR"

	# Recreate persistent directory symlink
	mkdir -p "${CONTAINER_HOME}/.config/engram"
	ln -sfn "${CONTAINER_HOME}/.config/engram" "${CONTAINER_HOME}/.engram" 2>/dev/null || true

	ok "Engram installed: $(${LOCAL_BIN}/engram version 2>&1 | head -1)"
}

install_tokensave() {
	local version="${1:-latest}"
	log "Installing TokenSave (${version})...."

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
	x86_64) arch="x86_64" ;;
	aarch64|arm64) arch="aarch64" ;;
	*)
		warn "Unsupported architecture: $(uname -m)"
		return 1
		;;
	esac

	# Create temp directory for download
	local TMP_DIR
	TMP_DIR=$(mktemp -d)
	local download_url=""
	local tar_name=""

	# Try to get release info via API
	if command -v curl &>/dev/null && command -v jq &>/dev/null; then
		local api_url="https://api.github.com/repos/aovestdipaperino/tokensave/releases/latest"
		if [[ "$version" != "latest" ]]; then
			api_url="https://api.github.com/repos/aovestdipaperino/tokensave/releases/tags/${version}"
		fi
		local release_info
		release_info=$(curl -s "$api_url" 2>/dev/null)

		if [[ $? -eq 0 && -n "$release_info" ]]; then
			# Check if response is an error
			if echo "$release_info" | jq -e '.message' >/dev/null 2>&1; then
				warn "API error: $(echo "$release_info" | jq -r '.message')"
			else
				# Find the asset matching our platform and arch
				local asset_url=""
				asset_url=$(echo "$release_info" | jq -r ".assets[]? | select(.name | contains(\"${arch}\") and contains(\"${platform}\") and endswith(\".tar.gz\") and (contains(\"bottle\") | not)) | .browser_download_url" 2>/dev/null | head -1)

				if [[ -n "$asset_url" && "$asset_url" != "null" ]]; then
					download_url="$asset_url"
					tar_name=$(basename "$asset_url")
				fi
			fi
		fi
	fi

	# Fallback to direct download URL construction if API fails
	if [[ -z "$download_url" ]]; then
		warn "Could not fetch release info via API, trying direct download..."
		local fallback_version="7.0.2"
		if [[ "$version" != "latest" ]]; then
			fallback_version="${version#v}"
		fi
		download_url="https://github.com/aovestdipaperino/tokensave/releases/download/v${fallback_version}/tokensave-v${fallback_version}-${arch}-${platform}.tar.gz"
		tar_name="tokensave-v${fallback_version}-${arch}-${platform}.tar.gz"
	fi

	log "Downloading from: $download_url"
	if ! curl -fsSL "$download_url" -o "${TMP_DIR}/${tar_name}"; then
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

	# Find tokensave binary and move it to LOCAL_BIN
	if [[ -f "tokensave" ]]; then
		mkdir -p "${LOCAL_BIN}"
		chmod +x tokensave
		mv tokensave "${LOCAL_BIN}/tokensave"
		ok "TokenSave binary installed successfully to ${LOCAL_BIN}/tokensave"
	else
		warn "tokensave binary not found in the extracted archive"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# Clean up
	rm -rf "$TMP_DIR"

	# Recreate persistent directory symlink
	mkdir -p "${CONTAINER_HOME}/.config/tokensave"
	ln -sfn "${CONTAINER_HOME}/.config/tokensave" "${CONTAINER_HOME}/.tokensave" 2>/dev/null || true

	ok "TokenSave installed: $(${LOCAL_BIN}/tokensave --version 2>&1 | head -1)"
}

install_oh_my_pi() {
	local version="${1:-latest}"
	log "Installing oh-my-pi (${version})..."

	# Detect platform and arch
	local platform=""
	if [[ "$(uname -s)" == "Linux" ]]; then
		platform="linux"
	elif [[ "$(uname -s)" == "Darwin" ]]; then
		platform="darwin"
	else
		warn "Unsupported platform: $(uname -s)"
		return 1
	fi

	local arch=""
	case "$(uname -m)" in
	x86_64) arch="x64" ;;
	aarch64|arm64) arch="arm64" ;;
	*)
		warn "Unsupported architecture: $(uname -m)"
		return 1
		;;
	esac

	local TMP_DIR
	TMP_DIR=$(mktemp -d)
	local download_url=""

	# Get release info via API
	if command -v curl &>/dev/null && command -v jq &>/dev/null; then
		local api_url="https://api.github.com/repos/can1357/oh-my-pi/releases/latest"
		if [[ "$version" != "latest" ]]; then
			api_url="https://api.github.com/repos/can1357/oh-my-pi/releases/tags/${version}"
		fi
		local release_info
		release_info=$(curl -s "$api_url" 2>/dev/null)

		if [[ $? -eq 0 && -n "$release_info" ]]; then
			if echo "$release_info" | jq -e '.message' >/dev/null 2>&1; then
				warn "API error: $(echo "$release_info" | jq -r '.message')"
			else
				# Find the asset matching our platform and arch
				download_url=$(echo "$release_info" | jq -r ".assets[]? | select(.name | contains(\"omp-${platform}-${arch}\")) | .browser_download_url" 2>/dev/null | head -1)
			fi
		fi
	fi

	if [[ -z "$download_url" ]]; then
		warn "Could not fetch release info via API"
		rm -rf "$TMP_DIR"
		return 1
	fi

	log "Downloading from: $download_url"
	local binary_name=$(basename "$download_url")
	if ! curl -fsSL "$download_url" -o "${TMP_DIR}/${binary_name}"; then
		warn "Download failed"
		rm -rf "$TMP_DIR"
		return 1
	fi

	mkdir -p "${LOCAL_BIN}"
	chmod +x "${TMP_DIR}/${binary_name}"
	mv "${TMP_DIR}/${binary_name}" "${LOCAL_BIN}/omp"

	# oh-my-pi stores its full user directory under ~/.omp (agent sessions,
	# secrets.yml, plugins, ...). That dir lives directly under HOME and is not
	# persistent, so symlink the whole ~/.omp to the persistent -local volume.
	# Config reads use plain fs paths that follow symlinks transparently.
	local omp_link="${CONTAINER_HOME}/.omp"
	local omp_backing="${CONTAINER_HOME}/.local/share/omp"
	mkdir -p "$omp_backing"
	if [[ -L "$omp_link" ]]; then
		ln -sfn "$omp_backing" "$omp_link"
	elif [[ -d "$omp_link" ]]; then
		cp -a "$omp_link/." "$omp_backing/" 2>/dev/null || true
		rm -rf "$omp_link"
		ln -sfn "$omp_backing" "$omp_link"
	else
		ln -sfn "$omp_backing" "$omp_link"
	fi

	rm -rf "$TMP_DIR"

	ok "oh-my-pi installed: $(${LOCAL_BIN}/omp --version 2>&1 | head -1)"
}

install_zerostack() {
	local version="${1:-latest}"
	log "Installing Zerostack (${version})..."

	# Detect platform and arch
	local platform=""
	if [[ "$(uname -s)" == "Linux" ]]; then
		platform="unknown-linux-gnu"
	elif [[ "$(uname -s)" == "Darwin" ]]; then
		platform="apple-darwin"
	else
		warn "Unsupported platform: $(uname -s)"
		return 1
	fi

	local arch=""
	case "$(uname -m)" in
	x86_64) arch="x86_64" ;;
	aarch64|arm64) arch="aarch64" ;;
	*)
		warn "Unsupported architecture: $(uname -m)"
		return 1
		;;
	esac

	local TMP_DIR
	TMP_DIR=$(mktemp -d)
	local download_url=""

	# Get release info via API
	if command -v curl &>/dev/null && command -v jq &>/dev/null; then
		local api_url="https://api.github.com/repos/gi-dellav/zerostack/releases/latest"
		if [[ "$version" != "latest" ]]; then
			api_url="https://api.github.com/repos/gi-dellav/zerostack/releases/tags/${version}"
		fi
		local release_info
		release_info=$(curl -s "$api_url" 2>/dev/null)

		if [[ $? -eq 0 && -n "$release_info" ]]; then
			if echo "$release_info" | jq -e '.message' >/dev/null 2>&1; then
				warn "API error: $(echo "$release_info" | jq -r '.message')"
			else
				# Prefer the musl build: it is statically linked and runs on systems
				# with older glibc. The gnu build requires GLIBC_2.38+ and fails on
				# older distros with "version GLIBC_2.38 not found".
				download_url=$(echo "$release_info" | jq -r ".assets[]? | select(.name | test(\"zerostack-${arch}-unknown-linux-musl.*\\.tar\\.gz$\")) | .browser_download_url" 2>/dev/null | head -1)

				# Fallback to gnu variant if musl not available
				if [[ -z "$download_url" ]]; then
					download_url=$(echo "$release_info" | jq -r ".assets[]? | select(.name | test(\"zerostack-${arch}-unknown-linux-gnu.*\\.tar\\.gz$\")) | .browser_download_url" 2>/dev/null | head -1)
				fi
			fi
		fi
	fi

	if [[ -z "$download_url" ]]; then
		warn "Could not fetch release info via API"
		rm -rf "$TMP_DIR"
		return 1
	fi

	log "Downloading from: $download_url"
	local tar_name=$(basename "$download_url")
	if ! curl -fsSL "$download_url" -o "${TMP_DIR}/${tar_name}"; then
		warn "Download failed"
		rm -rf "$TMP_DIR"
		return 1
	fi

	log "Extracting..."
	cd "$TMP_DIR"
	if ! tar xzf "${tar_name}"; then
		warn "Extraction failed"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# Find zerostack binary (may have versioned name like zerostack-x86_64-unknown-linux-musl)
	local zerostack_bin
	zerostack_bin=$(find . -type f -executable -name "*zerostack*" | grep -v "\.tar\.gz" | head -1)

	if [[ -n "$zerostack_bin" && -f "$zerostack_bin" ]]; then
		mkdir -p "${LOCAL_BIN}"
		chmod +x "$zerostack_bin"
		mv "$zerostack_bin" "${LOCAL_BIN}/zerostack"
		ok "Zerostack binary installed successfully to ${LOCAL_BIN}/zerostack"
	else
		warn "zerostack binary not found in the extracted archive"
		rm -rf "$TMP_DIR"
		return 1
	fi

	rm -rf "$TMP_DIR"

	ok "Zerostack installed: $(${LOCAL_BIN}/zerostack --version 2>&1 | head -1)"
}



install_qwen_code() {
	local version="${1:-latest}"
	log "Installing Qwen-Code (${version})..."

	# Detect platform and arch
	local platform=""
	if [[ "$(uname -s)" == "Linux" ]]; then
		platform="linux"
	elif [[ "$(uname -s)" == "Darwin" ]]; then
		platform="darwin"
	else
		warn "Unsupported platform: $(uname -s)"
		return 1
	fi

	local arch=""
	case "$(uname -m)" in
	x86_64) arch="x64" ;;
	aarch64|arm64) arch="arm64" ;;
	*)
		warn "Unsupported architecture: $(uname -m)"
		return 1
		;;
	esac

	local TMP_DIR
	TMP_DIR=$(mktemp -d)
	local download_url=""

	# Get release info via API
	if command -v curl &>/dev/null && command -v jq &>/dev/null; then
		local api_url="https://api.github.com/repos/QwenLM/qwen-code/releases/latest"
		if [[ "$version" != "latest" ]]; then
			api_url="https://api.github.com/repos/QwenLM/qwen-code/releases/tags/${version}"
		fi
		local release_info
		release_info=$(curl -s "$api_url" 2>/dev/null)

		if [[ $? -eq 0 && -n "$release_info" ]]; then
			if echo "$release_info" | jq -e '.message' >/dev/null 2>&1; then
				warn "API error: $(echo "$release_info" | jq -r '.message')"
			else
				# Find the asset matching our platform and arch
				download_url=$(echo "$release_info" | jq -r ".assets[]? | select(.name | contains(\"qwen-code-${platform}-${arch}\") and endswith(\".tar.gz\")) | .browser_download_url" 2>/dev/null | head -1)
			fi
		fi
	fi

	if [[ -z "$download_url" ]]; then
		warn "Could not fetch release info via API"
		rm -rf "$TMP_DIR"
		return 1
	fi

	log "Downloading from: $download_url"
	local tar_name=$(basename "$download_url")
	if ! curl -fsSL "$download_url" -o "${TMP_DIR}/${tar_name}"; then
		warn "Download failed"
		rm -rf "$TMP_DIR"
		return 1
	fi

	log "Extracting..."
	cd "$TMP_DIR"
	if ! tar xzf "${tar_name}"; then
		warn "Extraction failed"
		rm -rf "$TMP_DIR"
		return 1
	fi

	# qwen-code is a self-contained Node.js app: the archive contains a
	# `qwen-code/` directory with its own bundled node (node/bin/node) and a
	# launcher at bin/qwen that resolves node via a relative $ROOT path. We must
	# install the whole directory and exec the launcher by its real path (a
	# symlink would make $ROOT resolve to LOCAL_BIN, breaking node lookup).
	local qwen_launcher
	qwen_launcher=$(find . -type f -path "*/bin/qwen" 2>/dev/null | head -1)

	if [[ -z "$qwen_launcher" || ! -f "$qwen_launcher" ]]; then
		warn "qwen-code launcher not found in the extracted archive"
		rm -rf "$TMP_DIR"
		return 1
	fi

	local qwen_dir
	qwen_dir=$(cd "$(dirname "$(dirname "$qwen_launcher")")" && pwd)

	# Install into a persistent location: .local/share sits on the persistent
	# -local volume, so the app survives container recreation. We exec the real
	# path (no symlink) because qwen-code's launcher resolves $ROOT via a logical
	# `pwd`, which breaks when invoked through a symlink.
	local qwen_home="${CONTAINER_HOME}/.local/share/qwen-code"
	mkdir -p "$qwen_home"
	rm -rf "$qwen_home"
	cp -r "$qwen_dir" "$qwen_home"
	chmod +x "$qwen_home/bin/qwen"

	# qwen-code stores its entire user directory under ~/.qwen (settings.json,
	# QWEN.md, .env, memory, history, etc.). That dir lives directly under HOME
	# and is not persistent, so symlink the whole ~/.qwen to the persistent -local
	# volume. Config reads use plain fs paths that follow symlinks transparently
	# (unlike the launcher), so this preserves the full directory safely.
	local qwen_home_dir="${CONTAINER_HOME}/.local/share/qwen"
	local qwen_link="${CONTAINER_HOME}/.qwen"
	mkdir -p "$qwen_home_dir"
	if [[ -L "$qwen_link" ]]; then
		ln -sfn "$qwen_home_dir" "$qwen_link"
	elif [[ -d "$qwen_link" ]]; then
		# Pre-existing real dir (e.g. created by an older setup): migrate its
		# contents into the persistent backing dir, then replace with the symlink.
		cp -a "$qwen_link/." "$qwen_home_dir/" 2>/dev/null || true
		rm -rf "$qwen_link"
		ln -sfn "$qwen_home_dir" "$qwen_link"
	else
		ln -sfn "$qwen_home_dir" "$qwen_link"
	fi

	mkdir -p "${LOCAL_BIN}"
	cat > "${LOCAL_BIN}/qwen-code" << EOFWRAPPER
#!/bin/bash
exec "${CONTAINER_HOME}/.local/share/qwen-code/bin/qwen" "\$@"
EOFWRAPPER
	chmod +x "${LOCAL_BIN}/qwen-code"

	rm -rf "$TMP_DIR"

	ok "Qwen-Code installed to ${CONTAINER_HOME}/.qwen-code"
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
  pi           Pi coding agent (TypeScript)
  little-coder little-coder coding agent (TypeScript)
  empryo       Empryo Agent (CLI/TUI)
  engram       Engram Memory System (Go)
  tokensave    TokenSave Code Graph System (Rust)
  oh-my-pi     oh-my-pi shell configuration (Bash)
  zerostack    Zerostack development environment (Python)
  qwen-code    Qwen-Code LLM-based coding (Node.js)
  all          Install every supported agent

Examples:
  setup-agent.sh pi latest
  setup-agent.sh qwen-code
  setup-agent.sh all
EOF
	exit 0
}

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
	usage
fi

AGENT="${1,,}"

VERSION="${2:-}"

case "$AGENT" in
pi) install_pi "$VERSION" ;;
little-coder) install_little_coder "$VERSION" ;;
empryo) install_empryo "$VERSION" ;;
engram) install_engram "$VERSION" ;;
 tokensave) install_tokensave "$VERSION" ;;
 oh-my-pi) install_oh_my_pi "$VERSION" ;;
 zerostack) install_zerostack "$VERSION" ;;

qwen-code) install_qwen_code "$VERSION" ;;
watchdog) install_watchdog ;;
all)
	log "Installing all agents..."
	install_pi "$VERSION"
	install_little_coder "$VERSION"
	install_empryo "$VERSION"
	install_engram "$VERSION"
 	install_tokensave "$VERSION"
 	install_oh_my_pi "$VERSION"
 	install_zerostack "$VERSION"

	install_qwen_code "$VERSION"
	ok "All agents installed"
	;;
*) die "Unknown agent: $AGENT (run setup-agent.sh --help for usage)" ;;
esac
