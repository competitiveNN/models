#!/usr/bin/env bash
set -e

# Colors & log helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
log() { echo -e "${CYAN}▸${NC} $*"; }
ok() { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
die() { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

# ── Terminal resize propagation ─────────────────────────────────────────────
# Background loop to detect terminal size changes and send SIGWINCH to child processes
if [[ -t 0 ]]; then
	(
		prev_cols=0
		prev_lines=0
		while true; do
			if cols=$(tput cols 2>/dev/null) && lines=$(tput lines 2>/dev/null); then
				if [[ "$cols" != "$prev_cols" || "$lines" != "$prev_lines" ]]; then
					# Send SIGWINCH to current process group (all children)
					kill -WINCH 0 2>/dev/null || true
					prev_cols="$cols"
					prev_lines="$lines"
				fi
			fi
			sleep 1
		done
	) &
	SIZE_WATCH_PID=$!
	trap 'kill "$SIZE_WATCH_PID" 2>/dev/null' EXIT
fi

# Only show the banner when starting an interactive shell
if [ -t 0 ] && [ "$1" = "bash" ]; then
	echo ""
	echo "  ┌─────────────────────────────────────────────────┐"
	echo "  │         Multi-Agent CLI Environment              │"
	echo "  ├─────────────────────────────────────────────────┤"
	echo "  │  ⚠️  Mount volumes for persistence:             │"
	echo "  │     docker run -v /host/path:/home/agent ...     │"
	echo "  │  Preserves: npm packages, cache, agent data     │"
	echo "  │                                                  │"
	echo "  │  Agents are NOT pre-installed.                   │"
	echo "  │  Run setup-agent.sh to install them:             │"
	echo "  │                                                  │"
	echo "  │    setup-agent.sh all          — all agents      │"
	echo "  │    setup-agent.sh opencode     — OpenCode AI     │"
	echo "  │    setup-agent.sh pi           — Pi agent        │"
	echo "  │    setup-agent.sh little-coder — little-coder    │"
	echo "  │    setup-agent.sh soulforge    — SoulForge Agent │"
	echo "  │                                                  │"
	echo "  │  See setup-agent.sh --help for more.             │"
	echo "  └─────────────────────────────────────────────────┘"
	echo ""
fi

# ── Recreate symlinks for installed agents ───────────────────────────────────
# This ensures symlinks persist across container restarts

CONTAINER_HOME="${HOME:-/home/agent}"


# Recreate SoulForge symlink if installed
if [[ -d "${CONTAINER_HOME}/.local/share/soulforge" ]]; then
	ln -sf "${CONTAINER_HOME}/.local/share/soulforge" "${CONTAINER_HOME}/.soulforge" 2>/dev/null || true
fi

# ── Setup direnv for bash sessions ───────────────────────────────────────────
# Enable direnv hook for automatic environment loading
if command -v direnv &>/dev/null && [[ -f "${CONTAINER_HOME}/.bashrc" ]]; then
	# Check if direnv hook is already in .bashrc
	if ! grep -q 'direnv hook bash' "${CONTAINER_HOME}/.bashrc" 2>/dev/null; then
		echo 'eval "$(direnv hook bash)"' >>"${CONTAINER_HOME}/.bashrc"
	fi
fi

# ── Direnv environment loading for all commands ──────────────────────────────
# Check if direnv is available and if we should load environment for this command
if command -v direnv &>/dev/null && [[ $# -gt 0 ]]; then
	# Find the nearest .envrc file by walking up the directory tree
	find_envrc() {
		local dir="$PWD"
		while [[ "$dir" != "/" ]]; do
			if [[ -f "$dir/.envrc" ]]; then
				echo "$dir/.envrc"
				return 0
			fi
			dir="$(dirname "$dir")"
		done
		return 1
	}

# Check if this looks like an agent command (not setup, not bash, etc.)
  # We want to load direnv for actual agent executions
  if [[ "$1" != "bash" && "$1" != "setup-agent.sh" && "$1" != "direnv" ]]; then
		envrc_path="$(find_envrc)"
		if [[ -n "$envrc_path" ]]; then
			envrc_dir="$(dirname "$envrc_path")"
			echo "🔧 Loading direnv environment from $envrc_path"
			# Use direnv exec to load the environment and run the command
			exec direnv exec "$envrc_dir" "$@"
		fi
	fi
fi

exec "$@"
