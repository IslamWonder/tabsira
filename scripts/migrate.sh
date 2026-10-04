#!/usr/bin/env bash
# Run the database migrations: the geodata chain, the app chain, then the vectors chain.
#
# Usage: scripts/migrate.sh [message]
#   no message   upgrade the three chains to head
#   message      first autogenerate an app-chain revision with that message
#
# Geodata comes first because it is immutable reference data the app schema may
# point at; vectors come last because their keys point at app tables (decision
# 48). Reads DATABASE_URL from the root .env (CI injects it instead).

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# lib.sh belongs to the tooling; without it, define just what this script uses.
if [[ -f "$SCRIPT_DIR/lib.sh" ]]; then
	# shellcheck source=lib.sh
	source "$SCRIPT_DIR/lib.sh"
fi
declare -F log >/dev/null || log() { printf '[tabsira] %s\n' "$*"; }
declare -F ok >/dev/null || ok() { printf '[ ok ] %s\n' "$*"; }
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
cd "$REPO_ROOT/apps/api"

load_env
[[ -n "${DATABASE_URL:-}" ]] || die "DATABASE_URL is not set. Run scripts/setup-db.sh, which writes it into the root .env."
have uv || die "uv is not installed. See https://docs.astral.sh/uv/"

# psql does not understand SQLAlchemy's driver suffix.
PSQL_URL="${SYNC_DATABASE_URL:-$DATABASE_URL}"
PSQL_URL="${PSQL_URL/+asyncpg/}"
PSQL_URL="${PSQL_URL/+psycopg/}"

# The three schemas must exist before Alembic runs: each chain keeps its version
# table in its own schema. A schema that exists is left alone, so the role
# needs no CREATE privilege on the database when setup-db.sh made them.
if have psql; then
	log "Ensuring the app, geodata and vectors schemas exist..."
	for schema in app geodata vectors; do
		if [[ "$(psql "$PSQL_URL" -tA -c "SELECT 1 FROM pg_namespace WHERE nspname = '$schema'")" != "1" ]]; then
			psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "CREATE SCHEMA $schema" >/dev/null
		fi
	done
else
	warn "psql not found; assuming the app, geodata and vectors schemas already exist"
fi

if [[ -n "${1:-}" ]]; then
	log "Creating a new app migration: $1"
	uv run alembic revision --autogenerate -m "$1"
fi

log "Running the geodata chain..."
uv run alembic -c alembic_geodata/alembic.ini upgrade head

log "Running the app chain..."
uv run alembic upgrade head

log "Running the vectors chain..."
uv run alembic -c alembic_vectors/alembic.ini upgrade head

ok "Migrations completed"

# ── CI metrics ──────────────────────────────────────────────────────
if in_ci; then
	mkdir -p "${WORKSPACE:-.}/.ci_metrics"
	MIGRATIONS=$(find alembic/versions alembic_geodata/versions alembic_vectors/versions -name '2*.py' 2>/dev/null | wc -l | tr -d ' ')
	printf '{"stage":"migrations","status":"passed","count":%d}\n' "$MIGRATIONS" >"${WORKSPACE:-.}/.ci_metrics/migrations.json"
	ok "CI metrics: $MIGRATIONS migrations"
fi
