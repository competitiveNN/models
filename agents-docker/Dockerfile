FROM node:22-bookworm

LABEL maintainer="fra"
LABEL description="Multi-agent CLI environment — agents installed at runtime via setup-agent.sh"

# ── System dependencies ─────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV COLORTERM=truecolor

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev \
    git curl ca-certificates jq ripgrep ffmpeg sudo direnv vim-tiny \
    python3-dev python3-yaml python3-httpx kitty-terminfo ncurses-base ncurses-bin \
    lsof strace procps netcat-openbsd dnsutils less tree file neovim \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ── Create user ──────────────────────────────────────────────────────────────
ARG CONTAINER_USER=agent
ARG CONTAINER_UID=1001
ARG CONTAINER_GID=1001

RUN if getent passwd ${CONTAINER_UID} >/dev/null 2>&1; then \
        deluser --remove-home "$(getent passwd ${CONTAINER_UID} | cut -d: -f1)" 2>/dev/null || true; \
    fi \
    && groupadd -g ${CONTAINER_GID} ${CONTAINER_USER} 2>/dev/null || true \
    && useradd -m -u ${CONTAINER_UID} -g ${CONTAINER_GID} -d /home/${CONTAINER_USER} -s /bin/bash ${CONTAINER_USER} \
    && usermod -aG sudo ${CONTAINER_USER} \
    && echo "${CONTAINER_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt, /usr/bin/apt-get, /usr/local/bin/setup-agent.sh" >> /etc/sudoers

# ── Make /opt writable ───────────────────────────────────────────────────────
RUN chmod 777 /opt

# ── Home ─────────────────────────────────────────────────────────────────────
ENV CONTAINER_HOME=/home/${CONTAINER_USER}
ENV HOME=${CONTAINER_HOME}

# ── Bun (JavaScript runtime) ─────────────────────────────────────────────────
# Install bun to the agent's home directory
ENV BUN_INSTALL="${CONTAINER_HOME}/.bun"
RUN echo "Installing bun to ${BUN_INSTALL}" && \
    mkdir -p "${BUN_INSTALL}" && \
    curl -fsSL https://bun.sh/install | bash && \
    chown -R ${CONTAINER_UID}:${CONTAINER_GID} "${BUN_INSTALL}" && \
    echo "Bun installation complete. Bun path: $(which bun 2>/dev/null || echo 'not found')" && \
    ls -la "${BUN_INSTALL}/bin/" 2>/dev/null || echo "No bun bin directory"

# ── npm config ───────────────────────────────────────────────────────────────
ENV NPM_CONFIG_PREFIX=${CONTAINER_HOME}/.npm-global
ENV NPM_CONFIG_CACHE=${CONTAINER_HOME}/.npm-cache
ENV NPM_PREFIX=${CONTAINER_HOME}/.npm-global
ENV PATH="${CONTAINER_HOME}/.npm-global/bin:${CONTAINER_HOME}/.local/bin:${CONTAINER_HOME}/.juliaup/bin:${CONTAINER_HOME}/.bun/bin:${PATH}"
RUN mkdir -p ${NPM_CONFIG_PREFIX} ${NPM_CONFIG_CACHE} ${CONTAINER_HOME}/.local/bin ${CONTAINER_HOME}/.local/share/uv \
    && chown -R ${CONTAINER_UID}:${CONTAINER_GID} ${CONTAINER_HOME}/.npm-global ${CONTAINER_HOME}/.npm-cache ${CONTAINER_HOME}/.local

# ── uv (Python package manager) ──────────────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# ── Install Python 3.11 via uv ─────────────────────────────────────────────
RUN uv python install 3.14

# ── RTK (installed at base level, used by setup-agent.sh) ────────────────────
RUN curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# ── Setup script ─────────────────────────────────────────────────────────────
COPY setup-agent.sh /usr/local/bin/setup-agent.sh
RUN chmod +x /usr/local/bin/setup-agent.sh

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# ── Volumes for persistence ─────────────────────────────────────────────────
VOLUME ["/home/agent/.npm-global", "/home/agent/.npm-cache", "/home/agent/.local", "/home/agent/.cache", "/home/agent/.config/gh"]

# ── Config directory skeleton ────────────────────────────────────────────────


USER root
RUN mkdir -p "${CONTAINER_HOME}/.julia/juliaup" && chown -R ${CONTAINER_UID}:${CONTAINER_GID} "${CONTAINER_HOME}/.julia"

RUN mkdir -p "${CONTAINER_HOME}/.config/agent-gnupg" \
    && ln -sfn "${CONTAINER_HOME}/.config/agent-gnupg" "${CONTAINER_HOME}/.gnupg" \
    && chown -R ${CONTAINER_UID}:${CONTAINER_GID} "${CONTAINER_HOME}/.config/agent-gnupg" "${CONTAINER_HOME}/.gnupg"

USER ${CONTAINER_UID}
RUN curl -fsSL https://install.julialang.org | sh -s -- -y

USER root
RUN mkdir -p "${CONTAINER_HOME}/.cache" && chown -R ${CONTAINER_UID}:${CONTAINER_GID} "${CONTAINER_HOME}/.cache"

USER root
# ── Context7 MCP Server ──────────────────────────────────────────────────────
RUN npm install -g @upstash/context7-mcp

# ── AST-grep ────────────────────────────────────────────────────────────────
RUN npm install -g @ast-grep/cli

WORKDIR ${CONTAINER_HOME}

ENTRYPOINT ["entrypoint.sh"]
CMD ["bash"]
