#!/usr/bin/env bash
# Run the API with reload, bound to loopback (API_HOST and API_PORT from the root .env).
#
# Usage: scripts/dev-api.sh

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# lib.sh belongs to the tooling; without it, define just what this script uses.
if [[ -f "$SCRIPT_DIR/lib.sh" ]]; then
	# shellcheck source=lib.sh
	source "$SCRIPT_DIR/lib.sh"
fi
declare -F log >/dev/null || log() { printf '[tabsira] %s\n' "$*"; }
declare -F warn >/dev/null || warn() { printf '[warn] %s\n' "$*" >&2; }
declare -F die >/dev/null || die() {
	printf '[err ] %s\n' "$*" >&2
	exit 1
}
declare -F have >/dev/null || have() { command -v "$1" >/dev/null 2>&1; }
declare -F in_ci >/dev/null || in_ci() { [[ "${CI:-}" == "true" || "${CI:-}" == "1" || "${JENKINS_BUILD:-}" == "true" || "${JENKINS_BUILD:-}" == "1" ]]; }
declare -F load_env >/dev/null || load_env() {
	in_ci && return 0
	if [[ -f "$REPO_ROOT/.env" ]]; then
		set -a
		# shellcheck disable=SC1091
		. "$REPO_ROOT/.env"
		set +a
	else
		warn ".env not found at $REPO_ROOT/.env"
	fi
}

unset VIRTUAL_ENV
have uv || die "uv is not installed. See https://docs.astral.sh/uv/"
cd "$REPO_ROOT/apps/api"

load_env

# Fail with a readable message before uvicorn would bury it in a traceback.
log "Checking the configuration..."
uv run python -m src.cli.check_config

HOST="${API_HOST:-127.0.0.1}"
PORT="${API_PORT:-8000}"
log "API on http://$HOST:$PORT (docs at /docs, schema at /openapi.json). Ctrl+C to stop."
exec uv run uvicorn src.main:app --reload --reload-dir src --host "$HOST" --port "$PORT"
