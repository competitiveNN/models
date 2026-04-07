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
  echo "  │    setup-agent.sh gemini       — Gemini CLI      │"
  echo "  │    setup-agent.sh opencode     — OpenCode AI     │"
  echo "  │    setup-agent.sh qwen         — Qwen Code       │"
  echo "  │    setup-agent.sh kilo         — Kilo CLI        │"
  echo "  │    setup-agent.sh hermes       — Hermes Agent    │"
  echo "  │    setup-agent.sh soulforge    — SoulForge Agent │"
  echo "  │                                                  │"
  echo "  │  See setup-agent.sh --help for more.             │"
  echo "  └─────────────────────────────────────────────────┘"
	echo ""
fi

exec "$@"
