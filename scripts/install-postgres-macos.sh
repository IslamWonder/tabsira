#!/usr/bin/env bash
# The macOS counterpart of scripts/install-postgres.sh (which dispatches here on
# Darwin): PostgreSQL 18 with the extensions TABSIRA needs, and Redis, from
# Homebrew (decision 15).
#
#   postgresql@18, postgis, pgvector, redis   Homebrew core
#   timescaledb                               timescale/tap, built from source
#
# TimescaleDB is not in Homebrew core. The tap's formula builds the Community
# edition (retention and compression policies, decision 13); the Timescale
# License and why it does not change this repository's licence are explained in
# scripts/install-postgres.sh. timescaledb-tools is skipped: nothing here needs it.
#
# Homebrew keeps the server's settings in postgresql.auto.conf, so the preload
# list is written with ALTER SYSTEM and the superuser is your own macOS account
# (no sudo anywhere). The server and Redis run as login services
# (brew services), so they come back after a restart. Idempotent. The server is
# restarted once, when the preload list changed.
#
# Environment: PG_VERSION (default 18)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

PG_VERSION="${PG_VERSION:-18}"
PG_FORMULA="postgresql@${PG_VERSION}"
PRELOAD_REQUIRED="timescaledb,pg_stat_statements"

is_macos || die "this script is for macOS; on Ubuntu run scripts/install-postgres.sh"
require_cmd brew "Install Homebrew from https://brew.sh"

brew_has() { brew list --formula "$1" >/dev/null 2>&1; }

# ─── Packages ───────────────────────────────────────────────────────
for formula in "$PG_FORMULA" postgis pgvector redis; do
	if brew_has "$formula"; then
		ok "Already installed: $formula"
	else
		log "Installing $formula"
		brew install "$formula"
	fi
done

if brew_has timescaledb; then
	ok "Already installed: timescaledb"
else
	log "Installing timescaledb from timescale/tap"
	brew tap timescale/tap
	# Homebrew refuses formulae of a tap it does not trust; trust this one formula only.
	brew trust --formula timescale/tap/timescaledb
	brew install timescale/tap/timescaledb --without-timescaledb-tools
fi
# The formula builds into its own prefix: this puts the library and the control
# files where the server looks for them. Safe to repeat.
bash "$(brew --prefix timescaledb)/bin/timescaledb_move.sh" >/dev/null

PG_BIN="$(brew --prefix "$PG_FORMULA")/bin"
export PATH="$PG_BIN:$PATH"

# ─── The server ─────────────────────────────────────────────────────
brew services start "$PG_FORMULA" >/dev/null

wait_for_postgres() {
	local waited=0
	while ((waited < 30)); do
		psql -X -q -tA -d postgres -c "SELECT 1" >/dev/null 2>&1 && return 0
		sleep 1
		waited=$((waited + 1))
	done
	die "PostgreSQL did not come up within 30 seconds (see: $(brew --prefix)/var/log/${PG_FORMULA}.log)"
}
wait_for_postgres

current="$(psql -X -q -tA -d postgres -c 'SHOW shared_preload_libraries')"
if [[ "$current" == "$PRELOAD_REQUIRED" ]]; then
	ok "shared_preload_libraries already holds $PRELOAD_REQUIRED"
else
	log "shared_preload_libraries: '$current' -> '$PRELOAD_REQUIRED'"
	# A list setting takes one quoted item per library; one quoted string with
	# commas is read as a single library name and the server then fails to start.
	psql -X -q -d postgres -c "ALTER SYSTEM SET shared_preload_libraries = 'timescaledb', 'pg_stat_statements'"
	log "Restarting $PG_FORMULA"
	brew services restart "$PG_FORMULA" >/dev/null
	wait_for_postgres
	effective="$(psql -X -q -tA -d postgres -c 'SHOW shared_preload_libraries')"
	[[ "$effective" == "$PRELOAD_REQUIRED" ]] ||
		die "shared_preload_libraries is '$effective' after the restart, not '$PRELOAD_REQUIRED'"
	ok "shared_preload_libraries is now $effective"
fi

# ─── Every extension must be installable ────────────────────────────
missing=""
for ext in postgis pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements vector timescaledb; do
	[[ "$(psql -X -q -tA -d postgres -c "SELECT count(*) FROM pg_available_extensions WHERE name = '$ext'")" == "1" ]] || missing="$missing $ext"
done
[[ -z "$missing" ]] || die "these extensions are not available on this server:$missing"
[[ "$(psql -X -q -tA -d postgres -c 'SELECT rolsuper FROM pg_roles WHERE rolname = current_user')" == "t" ]] ||
	die "$(id -un) is not a PostgreSQL superuser here; scripts/setup-db.sh needs one"

# ─── Redis ──────────────────────────────────────────────────────────
brew services start redis >/dev/null
waited=0
until [[ "$(redis-cli ping 2>/dev/null)" == "PONG" ]]; do
	((waited < 15)) || die "Redis did not answer on 127.0.0.1:6379"
	sleep 1
	waited=$((waited + 1))
done
ok "Redis answers on 127.0.0.1:6379"

ok "PostgreSQL ${PG_VERSION} is ready: $(psql -X -q -tA -d postgres -c "SELECT string_agg(name || ' ' || default_version, ', ' ORDER BY name) FROM pg_available_extensions WHERE name IN ('postgis','vector','timescaledb','pg_stat_statements')")"
log "Add $PG_BIN to your PATH (psql, pg_dump, pg_restore). Next: bash scripts/setup-db.sh"
