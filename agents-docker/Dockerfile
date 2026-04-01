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
ARG BUILD_DATE

LABEL org.opencontainers.image.created="${BUILD_DATE}"

# ── System dependencies ─────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-dev \
    build-essential libffi-dev \
    git curl ca-certificates jq ripgrep ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── uv (fast Python package manager, needed by hermes) ──────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -sf /root/.local/bin/uv /usr/local/bin/uv

# ── npm agents (installed globally) ─────────────────────────────────────────

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

# ── Hermes Agent (Python-based, installed to /opt) ──────────────────────────
ENV HERMES_CODE=/opt/hermes-agent

RUN git clone --branch ${HERMES_AGENT_BRANCH} \
    https://github.com/NousResearch/hermes-agent.git ${HERMES_CODE}

WORKDIR ${HERMES_CODE}

RUN uv venv /opt/hermes-venv --python 3.11 \
    && VIRTUAL_ENV=/opt/hermes-venv uv pip install -e "." \
    && ln -sf /opt/hermes-venv/bin/hermes /usr/local/bin/hermes

# ── RTK AI (installed to /opt) ──────────────────────────────────────────────
ENV RTK_CODE=/opt/rtk

RUN git clone --branch master \
    https://github.com/rtk-ai/rtk.git ${RTK_CODE}

WORKDIR ${RTK_CODE}

RUN uv venv /opt/rtk-venv --python 3.11 \
    && VIRTUAL_ENV=/opt/rtk-venv uv pip install -e "." \
    && ln -sf /opt/rtk-venv/bin/rtk /usr/local/bin/rtk

# ── Create config directory structure ────────────────────────────────────────
ENV HERMES_HOME=/root/.hermes

RUN mkdir -p /root/.hermes/{cron,sessions,logs,pairing,hooks,image_cache,audio_cache,memories,skills,whatsapp/session} \
    && mkdir -p /root/.config \
    && if [ -f ${HERMES_CODE}/.env.example ]; then \
        cp ${HERMES_CODE}/.env.example /root/.hermes/.env; \
       fi \
    && if [ -f ${HERMES_CODE}/cli-config.yaml.example ]; then \
        cp ${HERMES_CODE}/cli-config.yaml.example /root/.hermes/config.yaml; \
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
    "kilo":      "$(kilo --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')", \
    "hermes":    "$(hermes --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')", \
    "rtk":       "$(rtk --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 'unknown')" \
  } \
}" > /etc/agents.json

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /root
ENTRYPOINT ["entrypoint.sh"]
CMD ["bash"]
