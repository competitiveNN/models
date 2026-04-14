#!/usr/bin/env bash
set -e

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
	echo "  │    setup-agent.sh copilot      — Copilot CLI     │"
	echo "  │    setup-agent.sh opencode     — OpenCode AI     │"
	echo "  │    setup-agent.sh kilo         — Kilo CLI        │"
	echo "  │    setup-agent.sh hermes       — Hermes Agent    │"
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

exec "$@"
