#!/usr/bin/env bash
# Install PostgreSQL 18 and the extensions TABSIRA needs on Ubuntu (DECISIONS.md,
# decision 15), and make the server load the two that must be preloaded.
#
#   postgresql-18, postgresql-18-postgis-3, postgresql-18-pgvector   PGDG
#   timescaledb-2-postgresql-18                                      Timescale
#
# pg_trgm, unaccent, pgcrypto, btree_gin, btree_gist and pg_stat_statements ship
# inside the postgresql-18 package itself.
#
# TimescaleDB licence, and why it does not come from PGDG. Hypertables are
# Apache-2.0, but compression, retention policies (add_retention_policy) and
# continuous aggregates are in the Timescale License (TSL) part, which the PGDG
# package postgresql-18-timescaledb leaves out ("Apache-licensed version"). Decision 13
# sets retention and compression per hypertable, so TABSIRA needs the Community
# build from Timescale's own apt repository. The TSL is source-available and free to
# run on our own servers; what it forbids is offering TimescaleDB itself to
# third parties as a database service. It is a server extension, not code linked
# into the application, so it does not change the licence of this repository. The
# two packages install the same files and cannot coexist.
#
# An existing PGDG repository, an existing Timescale repository and an existing
# server are used as they are. Idempotent. After a change to
# shared_preload_libraries the server is restarted once (a restart drops open
# connections of every database in this cluster).
#
# Environment: PG_VERSION (default 18)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

if is_macos; then
	exec bash "$SCRIPT_DIR/install-postgres-macos.sh"
fi

PG_VERSION="${PG_VERSION:-18}"
# Libraries the server must load at start. timescaledb goes first when absent.
PRELOAD_REQUIRED=(timescaledb pg_stat_statements)

require_ubuntu
require_sudo

# ─── apt repositories ───────────────────────────────────────────────
apt_install ca-certificates curl gnupg
as_root install -m 0755 -d /etc/apt/keyrings

apt_changed=false
if grep -rqs "apt.postgresql.org/pub/repos/apt" /etc/apt/sources.list /etc/apt/sources.list.d; then
	ok "PGDG apt repository already configured"
else
	log "Adding the PGDG apt repository for $OS_CODENAME"
	curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc |
		as_root gpg --dearmor --yes -o /etc/apt/keyrings/postgresql.gpg
	as_root chmod a+r /etc/apt/keyrings/postgresql.gpg
	echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt ${OS_CODENAME}-pgdg main" |
		as_root tee /etc/apt/sources.list.d/pgdg.list >/dev/null
	apt_changed=true
fi

TS_PACKAGE="timescaledb-2-postgresql-${PG_VERSION}"
TS_PGDG_PACKAGE="postgresql-${PG_VERSION}-timescaledb"
if dpkg -s "$TS_PGDG_PACKAGE" >/dev/null 2>&1; then
	die "$TS_PGDG_PACKAGE (the Apache-only build) is installed. TABSIRA needs the Community build ($TS_PACKAGE) for retention and compression policies, and the two cannot coexist. Remove the PGDG package (sudo apt-get remove $TS_PGDG_PACKAGE) and run this script again; check that no database you care about depends on it first."
fi
if ! dpkg -s "$TS_PACKAGE" >/dev/null 2>&1; then
	if grep -rqs "packagecloud.io/timescale/timescaledb" /etc/apt/sources.list /etc/apt/sources.list.d; then
		ok "Timescale apt repository already configured"
	else
		log "Adding the Timescale apt repository for $OS_CODENAME"
		curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey |
			as_root gpg --dearmor --yes -o /etc/apt/keyrings/timescaledb.gpg
		as_root chmod a+r /etc/apt/keyrings/timescaledb.gpg
		echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ ${OS_CODENAME} main" |
			as_root tee /etc/apt/sources.list.d/timescaledb.list >/dev/null
		apt_changed=true
	fi
fi

if $apt_changed; then
	as_root apt-get update -y
fi

# ─── Packages ───────────────────────────────────────────────────────
apt_install "postgresql-${PG_VERSION}" "postgresql-client-${PG_VERSION}" \
	"postgresql-${PG_VERSION}-postgis-3" "postgresql-${PG_VERSION}-postgis-3-scripts" \
	"postgresql-${PG_VERSION}-pgvector" "$TS_PACKAGE"

as_root systemctl enable --now postgresql >/dev/null 2>&1 || true

# ─── The server ─────────────────────────────────────────────────────
# From / so that the postgres user is not asked to enter a home directory.
pg_admin() { (cd / && sudo -u postgres psql -X -q -tA -v ON_ERROR_STOP=1 "$@"); }

wait_for_postgres() {
	local waited=0
	while ((waited < 30)); do
		pg_admin -c "SELECT 1" >/dev/null 2>&1 && return 0
		sleep 1
		waited=$((waited + 1))
	done
	die "PostgreSQL did not come up within 30 seconds (see: journalctl -u postgresql)"
}
wait_for_postgres

# shared_preload_libraries: keep what is there, add what is missing.
current="$(pg_admin -c 'SHOW shared_preload_libraries')"
want=()
IFS=',' read -r -a existing <<<"$current"
for lib in ${existing[@]+"${existing[@]}"}; do
	lib="$(printf '%s' "$lib" | tr -d " '\"")"
	[[ -n "$lib" ]] && want+=("$lib")
done
final=()
for lib in ${want[@]+"${want[@]}"}; do
	final+=("$lib")
done
for required in "${PRELOAD_REQUIRED[@]}"; do
	found=false
	for lib in ${final[@]+"${final[@]}"}; do
		[[ "$lib" == "$required" ]] && found=true
	done
	$found && continue
	if [[ "$required" == "timescaledb" ]]; then
		final=("$required" ${final[@]+"${final[@]}"})
	else
		final+=("$required")
	fi
done
joined=""
for lib in "${final[@]}"; do
	joined="${joined:+$joined,}$lib"
done

if [[ "$joined" == "$current" ]]; then
	ok "shared_preload_libraries already holds ${PRELOAD_REQUIRED[*]} ($current)"
else
	conf="$(pg_admin -c 'SHOW config_file')"
	backup="${conf}.tabsira-$(date +%Y%m%d%H%M%S).bak"
	log "shared_preload_libraries: '$current' -> '$joined'"
	log "Backing up $conf to $backup"
	as_root cp -p "$conf" "$backup"

	tmp="$(mktemp)"
	as_root awk -v new="shared_preload_libraries = '${joined}'  # (change requires restart)" '
		/^[[:space:]]*shared_preload_libraries[[:space:]]*=/ && !done { print new; done = 1; next }
		{ print }
		END { if (!done) print new }' "$conf" >"$tmp"
	# tee, not mv: the file keeps its owner and mode.
	as_root tee "$conf" <"$tmp" >/dev/null
	rm -f "$tmp"

	cluster="$(pg_lsclusters --no-header 2>/dev/null | awk -v v="$PG_VERSION" '$1 == v { print $2; exit }')"
	log "Restarting PostgreSQL ${PG_VERSION}/${cluster:-main}"
	if [[ -n "$cluster" ]] && as_root systemctl restart "postgresql@${PG_VERSION}-${cluster}" 2>/dev/null; then
		:
	elif have pg_ctlcluster && [[ -n "$cluster" ]]; then
		as_root pg_ctlcluster "$PG_VERSION" "$cluster" restart
	else
		as_root systemctl restart postgresql
	fi
	wait_for_postgres

	effective="$(pg_admin -c 'SHOW shared_preload_libraries')"
	if [[ "$effective" != "$joined" ]]; then
		die "shared_preload_libraries is '$effective' after the restart, not '$joined': another file (postgresql.auto.conf or conf.d) overrides $conf. The backup is $backup."
	fi
	ok "shared_preload_libraries is now $effective"
fi

# ─── Every extension must be installable ────────────────────────────
missing=""
for ext in postgis pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements vector timescaledb; do
	[[ "$(pg_admin -c "SELECT count(*) FROM pg_available_extensions WHERE name = '$ext'")" == "1" ]] || missing="$missing $ext"
done
[[ -z "$missing" ]] || die "these extensions are not available on this server:$missing"

ok "PostgreSQL ${PG_VERSION} is ready: $(pg_admin -c "SELECT string_agg(name || ' ' || default_version, ', ' ORDER BY name) FROM pg_available_extensions WHERE name IN ('postgis','vector','timescaledb','pg_stat_statements')")"
log "Next: bash scripts/setup-db.sh creates the role, databases, schemas and extensions."
