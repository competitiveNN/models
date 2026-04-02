#!/usr/bin/env bash
set -euo pipefail

HONCHO_DIR="${HONCHO_DIR:-$HOME/dev/models/honcho-setup/honcho}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
API_PORT="${API_PORT:-8000}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[honcho]${NC} $*"; }
ok() { echo -e "${GREEN}[honcho]${NC} $*"; }
warn() { echo -e "${YELLOW}[honcho]${NC} $*"; }
err() { echo -e "${RED}[honcho]${NC} $*" >&2; }

cleanup() {
	log "Shutting down..."
	if [[ -n "${DERIVER_PID:-}" ]] && kill -0 "$DERIVER_PID" 2>/dev/null; then
		kill "$DERIVER_PID" 2>/dev/null || true
		wait "$DERIVER_PID" 2>/dev/null || true
	fi
	if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" 2>/dev/null; then
		kill "$API_PID" 2>/dev/null || true
		wait "$API_PID" 2>/dev/null || true
	fi
	if [[ -d "$HONCHO_DIR" ]] && docker compose ps --status running -q database &>/dev/null; then
		log "Stopping database and redis containers..."
		docker compose stop database redis 2>/dev/null || true
	fi
	ok "Done."
}
trap cleanup EXIT INT TERM

# --- Dependency checks --------------------------------------------------------

check_command() {
	if ! command -v "$1" &>/dev/null; then
		err "'$1' is required but not installed."
		exit 1
	fi
}

check_command git
check_command docker
check_command curl

# --- Install uv if missing ---------------------------------------------------

if ! command -v uv &>/dev/null; then
	log "Installing uv..."
	curl -LsSf https://astral.sh/uv/install.sh | sh
	export PATH="$HOME/.local/bin:$PATH"
	if ! command -v uv &>/dev/null; then
		err "uv installation failed. Add ~/.local/bin to PATH and retry."
		exit 1
	fi
	ok "uv installed."
fi

# --- Clone or update repo -----------------------------------------------------

if [[ ! -d "$HONCHO_DIR/.git" ]]; then
	log "Cloning honcho into $HONCHO_DIR..."
	git clone --depth 1 https://github.com/plastic-labs/honcho.git "$HONCHO_DIR"
	ok "Cloned."
else
	log "Updating honcho..."
	git -C "$HONCHO_DIR" pull --ff-only || warn "Could not pull latest changes, using existing."
fi

cd "$HONCHO_DIR"

# --- Install Python dependencies ----------------------------------------------

log "Syncing Python dependencies..."
uv sync
ok "Dependencies installed."

# --- Docker: database + redis -------------------------------------------------

COMPOSE_FILE="docker-compose.yml"
if [[ ! -f "$COMPOSE_FILE" ]]; then
	cp docker-compose.yml.example "$COMPOSE_FILE"
	ok "Created docker-compose.yml from template."
fi

# Patch host ports to avoid conflicts if defaults are overridden
if [[ "$POSTGRES_PORT" != "5432" ]]; then
	sed -i "s/- 5432:5432/- ${POSTGRES_PORT}:5432/" "$COMPOSE_FILE"
fi
if [[ "$REDIS_PORT" != "6379" ]]; then
	sed -i "s/- 6379:6379/- ${REDIS_PORT}:6379/" "$COMPOSE_FILE"
fi

# Add :z label to redis volume for SELinux compatibility
sed -i 's|- ./redis-data:/data$|- ./redis-data:/data:z|' "$COMPOSE_FILE"

mkdir -p redis-data
chmod 777 redis-data

log "Starting PostgreSQL (pgvector) and Redis..."
docker compose up -d database redis

log "Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
	if docker compose exec -T database pg_isready -U postgres &>/dev/null; then
		ok "PostgreSQL is ready."
		break
	fi
	if [[ "$i" -eq 30 ]]; then
		err "PostgreSQL did not become ready in time."
		exit 1
	fi
	sleep 1
done

log "Waiting for Redis to be ready..."
for i in $(seq 1 30); do
	if docker compose exec -T redis redis-cli ping &>/dev/null; then
		ok "Redis is ready."
		break
	fi
	if [[ "$i" -eq 30 ]]; then
		err "Redis did not become ready in time."
		docker compose logs redis 2>&1 | tail -20 >&2
		exit 1
	fi
	sleep 1
done

# --- Environment file ---------------------------------------------------------

ENV_FILE=".env"
if [[ ! -f "$ENV_FILE" ]]; then
	cp .env.template "$ENV_FILE"

	# Set sensible defaults for local use
	sed -i "s|^DB_CONNECTION_URI=.*|DB_CONNECTION_URI=postgresql+psycopg://postgres:postgres@localhost:${POSTGRES_PORT}/postgres|" "$ENV_FILE"
	sed -i "s|^AUTH_USE_AUTH=.*|AUTH_USE_AUTH=false|" "$ENV_FILE"
	sed -i "s|^VECTOR_STORE_TYPE=.*|VECTOR_STORE_TYPE=pgvector|" "$ENV_FILE"
	sed -i "s|^CACHE_URL=.*|CACHE_URL=redis://localhost:${REDIS_PORT}/0?suppress=true|" "$ENV_FILE"
	sed -i "s|^CACHE_ENABLED=.*|CACHE_ENABLED=true|" "$ENV_FILE"

	ok "Created .env from template."
	warn "Edit $ENV_FILE to add your LLM API keys (LLM_OPENAI_API_KEY, LLM_ANTHROPIC_API_KEY)."
	warn "At least one LLM key is required for full functionality."
else
	ok ".env already exists, using existing configuration."
fi

# Export env vars so the server picks them up
set -a
source "$ENV_FILE"
set +a

# --- Database migrations ------------------------------------------------------

log "Running database migrations..."
uv run alembic upgrade head
ok "Migrations complete."

# --- Start API server ---------------------------------------------------------

log "Starting Honcho API server on port ${API_PORT}..."
uv run fastapi dev src/main.py --port "$API_PORT" &
API_PID=$!
sleep 2

if ! kill -0 "$API_PID" 2>/dev/null; then
	err "API server failed to start."
	exit 1
fi
ok "API server running (PID $API_PID) -> http://localhost:${API_PORT}"

# --- Start deriver (background worker) ----------------------------------------

log "Starting deriver worker..."
uv run python -m src.deriver &
DERIVER_PID=$!
sleep 1

if ! kill -0 "$DERIVER_PID" 2>/dev/null; then
	warn "Deriver failed to start (check LLM API keys). API server is still running."
else
	ok "Deriver running (PID $DERIVER_PID)."
fi

# --- Ready --------------------------------------------------------------------

echo ""
ok "Honcho is running!"
echo -e "  ${CYAN}API:${NC}      http://localhost:${API_PORT}"
echo -e "  ${CYAN}Docs:${NC}     http://localhost:${API_PORT}/docs"
echo -e "  ${CYAN}Database:${NC} localhost:${POSTGRES_PORT}"
echo -e "  ${CYAN}Redis:${NC}    localhost:${REDIS_PORT}"
echo ""
log "Press Ctrl+C to stop everything."

wait
