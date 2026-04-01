#!/usr/bin/env bash
set -e

# Only show the banner when starting an interactive shell
if [ -t 0 ] && [ "$1" = "bash" ]; then
	echo ""
	echo "  ┌─────────────────────────────────────────────────┐"
	echo "  │         Multi-Agent CLI Environment              │"
	echo "  ├─────────────────────────────────────────────────┤"
	echo "  │  copilot    - GitHub Copilot CLI                 │"
	echo "  │  gemini     - Google Gemini CLI                  │"
	echo "  │  opencode   - OpenCode AI                        │"
	echo "  │  qwen       - Qwen Code                         │"
	echo "  │  kilo       - Kilo CLI                           │"
	echo "  │  hermes     - Hermes Agent                       │"
	echo "  ├─────────────────────────────────────────────────┤"
	echo "  │  cat /etc/agents.json  — installed versions      │"
	echo "  └─────────────────────────────────────────────────┘"
	echo ""
fi

exec "$@"
