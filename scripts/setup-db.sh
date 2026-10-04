#!/usr/bin/env bash
# Create the local PostgreSQL role, databases, schemas and extensions for
# TABSIRA, and write the connection URLs into the root .env.
#
#   role        tabsira         login role; the password is generated once and
#                               kept in .env, never printed. CREATEDB on
#                               development and test hosts only: pytest-xdist makes
#                               one database per worker from a template. Never in
#                               production (see ENVIRONMENT below).
#   databases   tabsira         the application database
#               tabsira_test    the API test suite, and nothing else; not created
#                               when ENVIRONMENT is production
#               tabsira_template  development and test only: an empty copy of the
#                               setup (both schemas, every extension) marked as a
#                               template. The role is not a superuser and cannot
#                               create postgis, vector or timescaledb, so a database
#                               made for a pytest-xdist worker has to be copied
#                               from this one: CREATE DATABASE x TEMPLATE tabsira_template.
#                               It accepts no connections: TimescaleDB keeps a
#                               background session in every database that allows
#                               them, and PostgreSQL refuses to copy a template
#                               somebody is connected to.
#   schemas     app, geodata    owned by the role, in both databases
#   search_path app, geodata, public   set on the role
#   extensions  postgis pg_trgm unaccent pgcrypto btree_gin btree_gist
#               pg_stat_statements vector timescaledb   (DECISIONS.md, decision 15)
#               created in every database WITH SCHEMA public, the way the API
#               migrations do (the role's search_path finds them there)
#
# .env keys written (the file is created from .env.example when it is missing,
# is gitignored, and is made readable by you only):
#   DATABASE_URL        postgresql+asyncpg://tabsira:<password>@127.0.0.1:5432/tabsira
#   SYNC_DATABASE_URL   postgresql+psycopg://tabsira:<password>@127.0.0.1:5432/tabsira
#   TEST_DATABASE_URL   postgresql+asyncpg://tabsira:<password>@127.0.0.1:5432/tabsira_test
#
# Idempotent. Superuser steps use `sudo -u postgres` (peer authentication);
# the application role connects over 127.0.0.1 with its password, as the app will.
# Only objects named tabsira, tabsira_test and the role tabsira are touched: no
# other database or role on the server is read or changed.
#
# Needs: scripts/install-postgres.sh already run (packages, preloaded libraries).
# Environment:
#   PG_PORT       default 5432
#   ENVIRONMENT   development (default), test or production; taken from the
#                 environment, else from .env. Production gets neither CREATEDB
#                 nor a test database, and any CREATEDB left by an earlier
#                 development run is revoked.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

PG_HOST="127.0.0.1"
PG_PORT="${PG_PORT:-5432}"
DB_USER="tabsira"
DB_NAME="tabsira"
TEST_DB_NAME="tabsira_test"
TEMPLATE_DB_NAME="tabsira_template"
SCHEMAS=(app geodata)
EXTENSIONS=(postgis pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements vector timescaledb)
ENV_FILE="$REPO_ROOT/.env"

ENVIRONMENT="${ENVIRONMENT:-$(env_value "$ENV_FILE" ENVIRONMENT)}"
ENVIRONMENT="$(printf '%s' "${ENVIRONMENT:-development}" | tr '[:upper:]' '[:lower:]')"
case "$ENVIRONMENT" in
development | test)
	DATABASES=("$DB_NAME" "$TEST_DB_NAME" "$TEMPLATE_DB_NAME")
	CONNECTABLE=("$DB_NAME" "$TEST_DB_NAME")
	ROLE_FLAGS="CREATEDB"
	;;
production)
	DATABASES=("$DB_NAME")
	CONNECTABLE=("$DB_NAME")
	ROLE_FLAGS="NOCREATEDB"
	;;
*) die "ENVIRONMENT must be development, test or production (got '$ENVIRONMENT')" ;;
esac

require_cmd psql "Run: bash scripts/install-postgres.sh"
require_cmd openssl "Install openssl."
require_sudo

# psql_admin DB [psql arguments]: as the postgres superuser, from / so the
# postgres user is not asked to enter this checkout.
psql_admin() {
	local db="$1"
	shift
	# client_min_messages=warning keeps "already exists, skipping" out of re-runs.
	if [[ "$(id -un)" == "postgres" ]]; then
		(cd / && PGOPTIONS="-c client_min_messages=warning" psql -X -q -v ON_ERROR_STOP=1 -d "$db" "$@")
	else
		(cd / && sudo -u postgres env PGOPTIONS="-c client_min_messages=warning" psql -X -q -v ON_ERROR_STOP=1 -d "$db" "$@")
	fi
}
query() { psql_admin "$1" -tA -c "$2"; }

query postgres "SELECT 1" >/dev/null 2>&1 ||
	die "cannot reach PostgreSQL as the postgres user. Is it running? (systemctl status postgresql)"

# timescaledb and pg_stat_statements only work when the server preloads them.
preload="$(query postgres 'SHOW shared_preload_libraries')"
for lib in timescaledb pg_stat_statements; do
	[[ ",${preload//[ \'\"]/}," == *",$lib,"* ]] ||
		die "$lib is not in shared_preload_libraries ('$preload'). Run: bash scripts/install-postgres.sh"
done

# ─── Password: the one in .env, else a new one ──────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
	if [[ -f "$REPO_ROOT/.env.example" ]]; then
		cp "$REPO_ROOT/.env.example" "$ENV_FILE"
		log "Created .env from .env.example"
	else
		: >"$ENV_FILE"
		log "Created an empty .env"
	fi
fi
chmod 600 "$ENV_FILE"

DB_PASS="$(env_value "$ENV_FILE" DATABASE_URL | sed -E 's#^[^:]+://[^:@/]+:([^@]*)@.*$#\1#')"
# Keep an existing password only when it is long and URL-safe; a placeholder, a
# short one or anything that is not a URL with a password is replaced.
if [[ ! "$DB_PASS" =~ ^[A-Za-z0-9]{24,}$ ]]; then
	DB_PASS="$(openssl rand -hex 24)"
	log "Generated a new password for role $DB_USER"
fi

# ─── Role ───────────────────────────────────────────────────────────
# The password goes in through stdin: never on a command line, where any user
# on the machine could read it.
log "Ensuring role $DB_USER"
psql_admin postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
    CREATE ROLE $DB_USER LOGIN;
  END IF;
END
\$\$;
SQL
printf "ALTER ROLE %s WITH LOGIN PASSWORD '%s';\n" "$DB_USER" "$DB_PASS" | psql_admin postgres
psql_admin postgres -c "ALTER ROLE $DB_USER SET search_path = app, geodata, public;"
# CREATEDB lets pytest-xdist copy a template database per worker; it is a
# development convenience that a production role must not have.
psql_admin postgres -c "ALTER ROLE $DB_USER $ROLE_FLAGS;"
log "Role $DB_USER: $ROLE_FLAGS ($ENVIRONMENT)"

# ─── Databases ──────────────────────────────────────────────────────
for db in "${DATABASES[@]}"; do
	if [[ "$(query postgres "SELECT 1 FROM pg_database WHERE datname = '$db'")" != "1" ]]; then
		log "Creating database $db"
		psql_admin postgres -c "CREATE DATABASE $db OWNER $DB_USER ENCODING 'UTF8' TEMPLATE template0;"
	else
		ok "Database $db exists"
		psql_admin postgres -c "ALTER DATABASE $db OWNER TO $DB_USER;"
	fi

	# The template is closed to connections between runs; open it to work on it.
	if [[ "$db" == "$TEMPLATE_DB_NAME" ]]; then
		psql_admin postgres -c "ALTER DATABASE $db WITH ALLOW_CONNECTIONS true;"
	fi

	# ─── Schemas ────────────────────────────────────────────────────
	for schema in "${SCHEMAS[@]}"; do
		psql_admin "$db" -c "CREATE SCHEMA IF NOT EXISTS $schema AUTHORIZATION $DB_USER;"
		psql_admin "$db" -c "ALTER SCHEMA $schema OWNER TO $DB_USER;"
	done

	# ─── Extensions (created here with superuser rights; a migration only ever
	# finds them already present and never silently skips a missing one) ────
	for ext in "${EXTENSIONS[@]}"; do
		psql_admin "$db" -c "CREATE EXTENSION IF NOT EXISTS $ext SCHEMA public;"
		installed="$(query "$db" "SELECT extversion FROM pg_extension WHERE extname = '$ext'")"
		available="$(query "$db" "SELECT default_version FROM pg_available_extensions WHERE name = '$ext'")"
		if [[ "$installed" != "$available" ]]; then
			log "$db: updating $ext $installed -> $available"
			psql_admin "$db" -c "ALTER EXTENSION $ext UPDATE;" ||
				warn "$db: $ext could not be updated from $installed to $available"
		fi
	done
	if [[ "$db" == "$TEMPLATE_DB_NAME" ]]; then
		psql_admin postgres -c "ALTER DATABASE $db WITH IS_TEMPLATE true ALLOW_CONNECTIONS false;"
		# The TimescaleDB scheduler may still hold a session opened before the
		# switch, and a template with any session cannot be copied.
		psql_admin postgres -tA -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid()" >/dev/null
	fi
	ok "$db: schemas ${SCHEMAS[*]} and extensions ready"
done

# ─── .env ───────────────────────────────────────────────────────────
env_put "$ENV_FILE" DATABASE_URL "postgresql+asyncpg://$DB_USER:$DB_PASS@$PG_HOST:$PG_PORT/$DB_NAME"
env_put "$ENV_FILE" SYNC_DATABASE_URL "postgresql+psycopg://$DB_USER:$DB_PASS@$PG_HOST:$PG_PORT/$DB_NAME"
if [[ "$ENVIRONMENT" != "production" ]]; then
	env_put "$ENV_FILE" TEST_DATABASE_URL "postgresql+asyncpg://$DB_USER:$DB_PASS@$PG_HOST:$PG_PORT/$TEST_DB_NAME"
fi
ok "Connection URLs are in .env"

# ─── Verify as the application role, the way the app connects ───────
for db in "${CONNECTABLE[@]}"; do
	path="$(PGPASSWORD="$DB_PASS" PGCONNECT_TIMEOUT=5 psql -X -tA -h "$PG_HOST" -p "$PG_PORT" -U "$DB_USER" -d "$db" \
		-c 'SHOW search_path' 2>&1)" ||
		die "role $DB_USER cannot connect to $db over $PG_HOST:$PG_PORT: ${path//$DB_PASS/***}"
	[[ "$path" == "app, geodata, public" ]] || die "search_path of $DB_USER on $db is '$path'"
done

for db in "${CONNECTABLE[@]}"; do
	log "$db extensions: $(query "$db" "SELECT string_agg(extname || ' ' || extversion, ', ' ORDER BY extname) FROM pg_extension WHERE extname <> 'plpgsql'")"
done
ok "Database setup complete: ${DATABASES[*]}, role $DB_USER, search_path app, geodata, public"
