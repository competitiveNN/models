FROM node:22-bookworm

LABEL maintainer="fra"
LABEL description="Multi-agent CLI environment — agents installed at runtime via setup-agent.sh"

# ── System dependencies ─────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev \
    git curl ca-certificates jq ripgrep ffmpeg sudo direnv vim-tiny \
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
    && echo "${CONTAINER_USER} ALL=(ALL) NOPASSWD: /usr/bin/apt, /usr/bin/apt-get" >> /etc/sudoers

# ── Make /opt and /project writable ──────────────────────────────────────────
RUN chmod 777 /opt \
    && mkdir -p /project && chown ${CONTAINER_UID}:${CONTAINER_GID} /project

# ── Home ─────────────────────────────────────────────────────────────────────
ENV CONTAINER_HOME=/home/${CONTAINER_USER}
ENV HOME=${CONTAINER_HOME}

# ── npm config ───────────────────────────────────────────────────────────────
ENV NPM_CONFIG_PREFIX=${CONTAINER_HOME}/.npm-global
ENV NPM_CONFIG_CACHE=${CONTAINER_HOME}/.npm-cache
ENV NPM_PREFIX=${CONTAINER_HOME}/.npm-global
ENV PATH="${CONTAINER_HOME}/.npm-global/bin:${CONTAINER_HOME}/.local/bin:${CONTAINER_HOME}/.juliaup/bin:${PATH}"
RUN mkdir -p ${NPM_CONFIG_PREFIX} ${NPM_CONFIG_CACHE} ${CONTAINER_HOME}/.local/bin ${CONTAINER_HOME}/.local/share \
    && chown -R ${CONTAINER_UID}:${CONTAINER_GID} ${CONTAINER_HOME}/.npm-global ${CONTAINER_HOME}/.npm-cache ${CONTAINER_HOME}/.local

# ── uv (Python package manager) ──────────────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="${CONTAINER_HOME}/.local/bin:${PATH}"

# Install Python 3.11 via uv
RUN uv python install 3.11

# ── Julia via juliaup ─────────────────────────────────────────────────────────
RUN curl -fsSL https://install.julialang.org | sh

# ── RTK (installed at base level, used by setup-agent.sh) ────────────────────
RUN curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# ── Setup script ─────────────────────────────────────────────────────────────
COPY setup-agent.sh /usr/local/bin/setup-agent.sh
RUN chmod +x /usr/local/bin/setup-agent.sh

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# ── Volumes for persistence ─────────────────────────────────────────────────
VOLUME ["/home/agent/.npm-global", "/home/agent/.npm-cache", "/home/agent/.local", "/home/agent/.cache"]

# ── Config directory skeleton ────────────────────────────────────────────────
ENV HERMES_HOME=${CONTAINER_HOME}/.hermes

RUN mkdir -p ${CONTAINER_HOME}/.hermes/{cron,sessions,logs,pairing,hooks,image_cache,audio_cache,memories,skills,whatsapp/session} \
    && mkdir -p ${CONTAINER_HOME}/.copilot ${CONTAINER_HOME}/.config/opencode ${CONTAINER_HOME}/.cache \
    && chown -R ${CONTAINER_UID}:${CONTAINER_GID} ${CONTAINER_HOME}/.hermes ${CONTAINER_HOME}/.copilot ${CONTAINER_HOME}/.config ${CONTAINER_HOME}/.cache

USER ${CONTAINER_UID}
WORKDIR /project

ENTRYPOINT ["entrypoint.sh"]
CMD ["bash"]
