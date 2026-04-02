FROM node:22-bookworm

LABEL maintainer="fra"
LABEL description="Multi-agent CLI environment: copilot, gemini, opencode, qwen, kilo, hermes, rtk"

# ── Build args for version pinning ──────────────────────────────────────────
ARG COPILOT_VERSION=latest
ARG GEMINI_CLI_VERSION=latest
ARG OPENCODE_AI_VERSION=latest
ARG QWEN_CODE_VERSION=latest
ARG KILO_CLI_VERSION=latest
ARG HERMES_AGENT_BRANCH=main
ARG CONTAINER_USER=agent
ARG CONTAINER_UID=1001
ARG CONTAINER_GID=1001
ARG BUILD_DATE

LABEL org.opencontainers.image.created="${BUILD_DATE}"

# ── System dependencies ─────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-dev \
    build-essential libffi-dev \
    git curl ca-certificates jq ripgrep ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Create user before any package installation ─────────────────────────────
RUN groupadd -g ${CONTAINER_GID} ${CONTAINER_USER} 2>/dev/null || true \
    && useradd -m -u ${CONTAINER_UID} -g ${CONTAINER_GID} -d /home/${CONTAINER_USER} -s /bin/bash ${CONTAINER_USER}

# ── Make /opt writable by container user ─────────────────────────────────────
RUN chmod 777 /opt

# ── Set home directory env var ─────────────────────────────────────────────
ENV CONTAINER_HOME=/home/${CONTAINER_USER}
ENV HOME=${CONTAINER_HOME}

# ── Switch to user for tool installations ──────────────────────────────────────
USER ${CONTAINER_UID}
WORKDIR ${CONTAINER_HOME}

# ── Configure npm for user-global installs ─────────────────────────────────────
ENV NPM_CONFIG_PREFIX=${CONTAINER_HOME}/.npm-global
ENV NPM_CONFIG_CACHE=${CONTAINER_HOME}/.npm-cache
ENV PATH="${CONTAINER_HOME}/.npm-global/bin:${CONTAINER_HOME}/.local/bin:${PATH}"
RUN mkdir -p ${NPM_CONFIG_PREFIX} ${NPM_CONFIG_CACHE}


# ── npm agents (installed globally as user) ───────────────────────────────────

# 1. GitHub Copilot CLI
RUN if [ "$COPILOT_VERSION" = "latest" ]; then \
        npm install -g @github/copilot; \
    else \
        npm install -g "@github/copilot@${COPILOT_VERSION}"; \
    fi

# 2. Google Gemini CLI
RUN if [ "$GEMINI_CLI_VERSION" = "latest" ]; then \
        npm install -g @google/gemini-cli; \
    else \
        npm install -g "@google/gemini-cli@${GEMINI_CLI_VERSION}"; \
    fi

# 3. OpenCode AI
RUN if [ "$OPENCODE_AI_VERSION" = "latest" ]; then \
        npm install -g opencode-ai; \
    else \
        npm install -g "opencode-ai@${OPENCODE_AI_VERSION}"; \
    fi

# 4. Qwen Code
RUN if [ "$QWEN_CODE_VERSION" = "latest" ]; then \
        npm install -g @qwen-code/qwen-code; \
    else \
        npm install -g "@qwen-code/qwen-code@${QWEN_CODE_VERSION}"; \
    fi

# 5. Kilo CLI
RUN if [ "$KILO_CLI_VERSION" = "latest" ]; then \
        npm install -g @kilocode/cli; \
    else \
        npm install -g "@kilocode/cli@${KILO_CLI_VERSION}"; \
    fi

# ── uv (Python package manager, needed by hermes) ────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="${CONTAINER_HOME}/.local/bin:${PATH}"

# ── Hermes Agent (Python-based, installed to /opt) ────────────────────────────
ENV HERMES_CODE=/opt/hermes-agent

RUN git clone --branch ${HERMES_AGENT_BRANCH} \
    https://github.com/NousResearch/hermes-agent.git ${HERMES_CODE}

WORKDIR ${HERMES_CODE}

RUN uv venv /opt/hermes-venv --python 3.11 \
    && VIRTUAL_ENV=/opt/hermes-venv uv pip install -e "." \
    && ln -sf /opt/hermes-venv/bin/hermes ${CONTAINER_HOME}/.local/bin/hermes

# ── RTK AI (CLI tool, installed via install script) ──────────────────────────
RUN curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh

# ── Initialize RTK for all supported agents ──────────────────────────────────
RUN mkdir -p ${CONTAINER_HOME}/.gemini ${CONTAINER_HOME}/.copilot ${CONTAINER_HOME}/.config/opencode \
    && rtk init -g --auto-patch \
    && rtk init -g --gemini --auto-patch \
    && rtk init -g --opencode --auto-patch \
    && rtk init -g --copilot --auto-patch

# ── Create config directory structure ────────────────────────────────────────
ENV HERMES_HOME=${CONTAINER_HOME}/.hermes

RUN mkdir -p ${CONTAINER_HOME}/.hermes/{cron,sessions,logs,pairing,hooks,image_cache,audio_cache,memories,skills,whatsapp/session} \
    && mkdir -p ${CONTAINER_HOME}/.config \
    && if [ -f ${HERMES_CODE}/.env.example ]; then \
        cp ${HERMES_CODE}/.env.example ${CONTAINER_HOME}/.hermes/.env; \
       fi \
    && if [ -f ${HERMES_CODE}/cli-config.yaml.example ]; then \
        cp ${HERMES_CODE}/cli-config.yaml.example ${CONTAINER_HOME}/.hermes/config.yaml; \
       fi

# ── Verify all agents are installed ─────────────────────────────────────────
RUN echo "=== Verifying installed agents ===" \
    && copilot --version     2>&1 | head -1 || echo "copilot: installed" \
    && gemini --version      2>&1 | head -1 || echo "gemini: installed" \
    && opencode --version    2>&1 | head -1 || echo "opencode: installed" \
    && qwen --version        2>&1 | head -1 || echo "qwen: installed" \
    && kilo --version        2>&1 | head -1 || echo "kilo: installed" \
    && hermes --version      2>&1 | head -1 || echo "hermes: installed" \
    && rtk --version         2>&1 | head -1 || echo "rtk: installed" \
    && echo "=== All agents installed ==="

# Metadata
RUN echo "{ \
  \"build_date\": \"${BUILD_DATE}\", \
  \"agents\": { \
    \"copilot\":   \"$(copilot --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\", \
    \"gemini\":    \"$(gemini --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\", \
    \"opencode\":  \"$(opencode --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\", \
    \"qwen\":      \"$(qwen --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\", \
    \"kilo\":      \"$(kilo --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\", \
    \"hermes\":    \"$(hermes --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\", \
    \"rtk\":       \"$(rtk --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')\" \
  } \
}"> ${CONTAINER_HOME}/agents.json

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY --chown=1001:1001 entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR ${CONTAINER_HOME}
ENTRYPOINT ["entrypoint.sh"]
CMD ["bash"]
