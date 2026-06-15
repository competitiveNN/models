#!/usr/bin/env bash
set -e

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

# Determine agent user from home directory (used when entrypoint runs as root)
AGENT_USER="$(getent passwd | awk -F: -v home="$CONTAINER_HOME" '$6==home {print $1; exit}')"
if [[ -z "$AGENT_USER" ]]; then AGENT_USER="agent"; fi

# If running as root and not already switched to agent, set up a writable overlay for ~/.ssh
if [[ "$(id -u)" -eq 0 && "${AS_AGENT:-0}" != "1" ]]; then
  SSH_DIR="${CONTAINER_HOME}/.ssh"
  LOWER_BIND="${CONTAINER_HOME}/.ssh-lower"
  OVERLAY_BASE="${CONTAINER_HOME}/.ssh-overlay"
  UPPER_DIR="${OVERLAY_BASE}/upper"
  WORK_DIR="${OVERLAY_BASE}/work"

  mkdir -p "${SSH_DIR}" "${LOWER_BIND}" "${UPPER_DIR}" "${WORK_DIR}"
  chown -R "${AGENT_USER}:""${AGENT_USER}" "${OVERLAY_BASE}" "${UPPER_DIR}" "${WORK_DIR}" || true

  # If already overlay mounted, skip
  if awk -v t="$SSH_DIR" '($2==t && $3=="overlay"){found=1; exit} END{exit !found}' /proc/mounts 2>/dev/null; then
    :
  else
    # Bind-mount the current ssh dir to a lowerdir location
    if ! awk -v t="$LOWER_BIND" '($2==t){found=1; exit} END{exit !found}' /proc/mounts 2>/dev/null; then
      if ! mount --bind "${SSH_DIR}" "${LOWER_BIND}" 2>/dev/null; then
        warn "Failed to bind-mount ${SSH_DIR} to ${LOWER_BIND}; overlay may not be possible"
      fi
    fi

    # Attempt to mount overlay on top of SSH_DIR
    if mount -t overlay overlay -o lowerdir="${LOWER_BIND}",upperdir="${UPPER_DIR}",workdir="${WORK_DIR}" "${SSH_DIR}" 2>/dev/null; then
      chown -R "${AGENT_USER}:""${AGENT_USER}" "${UPPER_DIR}" "${WORK_DIR}" || true
      ok "Mounted writable overlay on ${SSH_DIR}; host files remain untouched"
    else
      # Overlay mount failed
      if awk -v t="$SSH_DIR" '($2==t){found=1; exit} END{exit !found}' /proc/mounts 2>/dev/null; then
        warn "Could not mount overlay on ${SSH_DIR}. Container likely lacks CAP_SYS_ADMIN; run container with --cap-add SYS_ADMIN to enable overlay. No changes made to host files."
      else
        # Not a mountpoint — fallback to copying into a local directory
        BACKUP="${CONTAINER_HOME}/.ssh-backup-$(date +%s)"
        mv "${SSH_DIR}" "${BACKUP}" 2>/dev/null || true
        mkdir -p "${SSH_DIR}"
        if cp -a "${BACKUP}/." "${SSH_DIR}" 2>/dev/null; then
          chown -R "${AGENT_USER}:""${AGENT_USER}" "${SSH_DIR}" || true
          ok "Copied existing SSH content into ${SSH_DIR} (no host modification)"
        else
          warn "Failed to copy SSH content to ${SSH_DIR}; leaving as-is."
        fi
      fi
    fi
  fi

  # Recreate SoulForge symlink if installed
  if [[ -d "${CONTAINER_HOME}/.local/share/soulforge" ]]; then
    ln -sf "${CONTAINER_HOME}/.local/share/soulforge" "${CONTAINER_HOME}/.soulforge" 2>/dev/null || true
  fi

  # Re-exec the entrypoint as the agent user to run the rest of the script in user context
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u "${AGENT_USER}" -- env AS_AGENT=1 /usr/local/bin/entrypoint.sh "$@"
  else
    cmd=""
    for a in "$@"; do
      cmd="${cmd} $(printf '%q' "$a")"
    done
    exec su - "${AGENT_USER}" -c "AS_AGENT=1 /usr/local/bin/entrypoint.sh ${cmd}"
  fi
fi

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
