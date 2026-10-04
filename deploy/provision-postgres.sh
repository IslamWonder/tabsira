#!/usr/bin/env bash
# Provision PostgreSQL 18 on the production DATA host (Ubuntu 24.04 or 26.04).
# Native packages, no Docker, listens on loopback and the Netbird address only,
# one pg_hba line for the application host, a nightly local dump with rotation.
#
# What it does, in order:
#   1. PGDG and TimescaleDB apt repositories; installs postgresql-18 with
#      PostGIS, pgvector and TimescaleDB.
#   2. UTC, a kernel setting, a managed tuning file sized from the host
#      (conf.d/90-tabsira.conf; shared_preload_libraries = pg_stat_statements,
#      timescaledb).
#   3. listen_addresses = 127.0.0.1 and DATA_HOST_VPN_IP (default: the address
#      on wt0). Never every interface.
#   4. pg_hba.conf, one managed block: the application role from
#      APP_HOST_VPN_IP/32 with scram-sha-256. No trust lines, no ranges.
#   5. Roles (the application role, and a read-only one when DB_RO_USER is
#      set; both with search_path app, geodata, public), the database, the
#      schemas app and geodata, and the nine extensions: postgis, vector,
#      timescaledb, pg_trgm, unaccent, pgcrypto, btree_gin, btree_gist,
#      pg_stat_statements. A missing one is an error.
#   6. A systemd timer: nightly dump into BACKUP_DIR, verified, rotated.
#   7. Verification of the listener and of the application login.
#
# Passwords are generated on the first run and kept in /etc/tabsira/postgres.env
# (root only); a later run re-applies them. Nothing secret is printed except the
# URLs for the application host's environment file, at the end.
#
# Usage (as root, on the data host):
#   APP_HOST_VPN_IP=<netbird address of the app host> deploy/provision-postgres.sh [--dry-run]
#
# Environment: APP_HOST_VPN_IP (required), DATA_HOST_VPN_IP, VPN_IFACE (wt0),
# PG_VERSION (18), DB_NAME (tabsira), DB_USER (tabsira), DB_RO_USER (none),
# PG_LOCALE (en_US.UTF-8), PG_MAX_CONNECTIONS (100), BACKUP_DIR
# (/var/backups/tabsira), BACKUP_KEEP_DAYS (14), BACKUP_KEEP_MIN (3).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"
# shellcheck disable=SC1091
source "$DEPLOY_DIR/net-lib.sh"

[[ "${1:-}" == "--dry-run" ]] && set_dry_run
PG_VERSION="${PG_VERSION:-18}"
VPN_IFACE="${VPN_IFACE:-wt0}"
DB_NAME="${DB_NAME:-tabsira}"
DB_USER="${DB_USER:-tabsira}"
DB_RO_USER="${DB_RO_USER:-}"
PG_LOCALE="${PG_LOCALE:-en_US.UTF-8}"
PG_MAX_CONNECTIONS="${PG_MAX_CONNECTIONS:-100}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tabsira}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
BACKUP_KEEP_MIN="${BACKUP_KEEP_MIN:-3}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-/etc/tabsira/postgres.env}"
EXTENSIONS="postgis vector timescaledb pg_trgm unaccent pgcrypto btree_gin btree_gist pg_stat_statements"

[[ "$PG_VERSION" =~ ^[0-9]+$ ]] || die "PG_VERSION must be a major version number."
[[ "$DB_NAME" =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_NAME must be a plain identifier."
[[ "$DB_USER" =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_USER must be a plain identifier."
[[ -z "$DB_RO_USER" || "$DB_RO_USER" =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_RO_USER must be a plain identifier."
require_app_host

if is_dry; then
	banner "DRY RUN: PostgreSQL $PG_VERSION on the data host"
	log "listen        127.0.0.1 and ${DATA_HOST_VPN_IP:-the address on $VPN_IFACE}"
	log "pg_hba        host $DB_NAME $DB_USER $APP_HOST_VPN_IP/32 scram-sha-256"
	log "database      $DB_NAME owned by $DB_USER${DB_RO_USER:+, read-only role $DB_RO_USER}; search_path app, geodata, public"
	log "extensions    $EXTENSIONS"
	log "backups       nightly to $BACKUP_DIR, $BACKUP_KEEP_DAYS days, newest $BACKUP_KEEP_MIN always kept"
	log "credentials   $CREDENTIALS_FILE (root only)"
	ok "Dry run complete: nothing was changed."
	exit 0
fi

[[ $EUID -eq 0 ]] || die "Run as root (sudo)."
have ip || die "iproute2 is required."
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || die "This script targets Ubuntu (found: ${ID:-unknown})."
CODENAME="${VERSION_CODENAME:?no VERSION_CODENAME in /etc/os-release}"

LISTEN_ADDR="$(resolve_listen_addr "${DATA_HOST_VPN_IP:-}" "$VPN_IFACE")"
CONF_DIR="/etc/postgresql/$PG_VERSION/main"
TUNING_FILE="$CONF_DIR/conf.d/90-tabsira.conf"
HBA_FILE="$CONF_DIR/pg_hba.conf"

pg() { runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q "$@"; }
pg_scalar() { runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -tA "$@"; }

# A password from the credentials file, else made now (letters and digits only: it sits in a URL).
password_for() {
	local key="$1" value=""
	[[ -r "$CREDENTIALS_FILE" ]] && value="$(sed -n "s/^${key}=//p" "$CREDENTIALS_FILE" | tail -n 1)"
	[[ -n "$value" ]] || value="$(openssl rand -hex 24)"
	printf '%s' "$value"
}

# ─── Packages ───────────────────────────────────────────────────────
log "Adding the PGDG and TimescaleDB apt repositories"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg openssl locales >/dev/null
install -m 0755 -d /etc/apt/keyrings
[[ -s /etc/apt/keyrings/postgresql.gpg ]] ||
	curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg
[[ -s /etc/apt/keyrings/timescaledb.gpg ]] ||
	curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg
chmod a+r /etc/apt/keyrings/postgresql.gpg /etc/apt/keyrings/timescaledb.gpg
echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main" >/etc/apt/sources.list.d/pgdg.list
echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/ubuntu/ ${CODENAME} main" >/etc/apt/sources.list.d/timescaledb.list
apt-get update -qq

grep -qix "${PG_LOCALE/UTF-8/utf8}" < <(locale -a) || {
	grep -qxF "$PG_LOCALE UTF-8" /etc/locale.gen || echo "$PG_LOCALE UTF-8" >>/etc/locale.gen
	locale-gen "$PG_LOCALE" >/dev/null
}
log "Installing PostgreSQL $PG_VERSION, PostGIS, pgvector, TimescaleDB"
LANG="$PG_LOCALE" LC_ALL="$PG_LOCALE" apt-get install -y -qq \
	"postgresql-$PG_VERSION" "postgresql-client-$PG_VERSION" \
	"postgresql-$PG_VERSION-postgis-3" "postgresql-$PG_VERSION-pgvector" \
	"timescaledb-2-postgresql-$PG_VERSION" >/dev/null
pg_lsclusters -h | awk '{ print $1 "/" $2 }' | grep -qx "$PG_VERSION/main" ||
	pg_createcluster --locale "$PG_LOCALE" "$PG_VERSION" main
PG_PORT="$(pg_lsclusters -h | awk -v v="$PG_VERSION" '$1 == v && $2 == "main" { print $3 }')"
[[ "$PG_PORT" =~ ^[0-9]+$ ]] || die "Could not read the port of cluster $PG_VERSION/main."

# ─── System and tuning ──────────────────────────────────────────────
[[ "$(timedatectl show -p Timezone --value 2>/dev/null || true)" == UTC ]] || timedatectl set-timezone UTC || true
printf 'vm.swappiness = 10\n' >/etc/sysctl.d/90-tabsira-postgres.conf
sysctl -q --system >/dev/null 2>&1 || warn "Some sysctl keys could not be applied."

MEM_MB=$(($(awk '/^MemTotal:/ { print $2 }' /proc/meminfo) / 1024))
CPUS="$(nproc)"
SHARED_MB=$((MEM_MB / 4))
CACHE_MB=$((MEM_MB * 3 / 4))
WORK_KB=$(((MEM_MB * 1024 - SHARED_MB * 1024) / (PG_MAX_CONNECTIONS * 3)))
((WORK_KB < 4096)) && WORK_KB=4096
((WORK_KB > 65536)) && WORK_KB=65536
MAINT_MB=$((MEM_MB / 16))
((MAINT_MB < 64)) && MAINT_MB=64
((MAINT_MB > 2048)) && MAINT_MB=2048
GATHER=$((CPUS / 2))
((GATHER < 1)) && GATHER=1
((GATHER > 4)) && GATHER=4

grep -qE "^\s*include_dir\s*=\s*'conf.d'" "$CONF_DIR/postgresql.conf" || echo "include_dir = 'conf.d'" >>"$CONF_DIR/postgresql.conf"
install -d -o postgres -g postgres -m 0755 "$CONF_DIR/conf.d"
log "Writing $TUNING_FILE"
cat >"$TUNING_FILE" <<EOF
# Managed by deploy/provision-postgres.sh, rewritten on every run.
# Sized for ${MEM_MB} MB RAM and $CPUS CPU(s). Change the script's variables and run it again.
listen_addresses = '127.0.0.1,$LISTEN_ADDR'
max_connections = $PG_MAX_CONNECTIONS
password_encryption = scram-sha-256
shared_buffers = ${SHARED_MB}MB
effective_cache_size = ${CACHE_MB}MB
work_mem = ${WORK_KB}kB
maintenance_work_mem = ${MAINT_MB}MB
wal_compression = zstd
checkpoint_completion_target = 0.9
random_page_cost = 1.1
effective_io_concurrency = 200
max_parallel_workers_per_gather = $GATHER
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.02
idle_in_transaction_session_timeout = 10min
tcp_keepalives_idle = 60
shared_preload_libraries = 'pg_stat_statements,timescaledb'
pg_stat_statements.track = all
track_io_timing = on
log_min_duration_statement = 500
log_checkpoints = on
log_lock_waits = on
timezone = 'UTC'
log_timezone = 'UTC'
EOF
chown postgres:postgres "$TUNING_FILE"

# ─── pg_hba.conf: the application host, and nobody else ────────────
HBA_BEGIN="# BEGIN tabsira (managed by deploy/provision-postgres.sh)"
HBA_END="# END tabsira"
HBA_TMP="$(mktemp)"
awk -v b="$HBA_BEGIN" -v e="$HBA_END" '$0 == b { skip = 1; next } $0 == e { skip = 0; next } skip { next } { print }' "$HBA_FILE" >"$HBA_TMP"
{
	echo
	echo "$HBA_BEGIN"
	printf 'host\t%s\t%s\t%s/32\tscram-sha-256\n' "$DB_NAME" "$DB_USER" "$APP_HOST_VPN_IP"
	[[ -z "$DB_RO_USER" ]] || printf 'host\t%s\t%s\t%s/32\tscram-sha-256\n' "$DB_NAME" "$DB_RO_USER" "$APP_HOST_VPN_IP"
	echo "$HBA_END"
} >>"$HBA_TMP"
install -o postgres -g postgres -m 0640 "$HBA_TMP" "$HBA_FILE"
rm -f "$HBA_TMP"

systemctl enable postgresql >/dev/null 2>&1 || true
systemctl restart "postgresql@$PG_VERSION-main"
wait_until 60 pg_isready -q -p "$PG_PORT" || die "PostgreSQL did not come back; see journalctl -u postgresql@$PG_VERSION-main."
ok "PostgreSQL is up: $(pg_scalar -c 'SHOW server_version;')"

# ─── Roles, database, schemas, extensions ───────────────────────────
DB_PASSWORD="$(password_for DB_PASSWORD)"
RO_PASSWORD=""
[[ -z "$DB_RO_USER" ]] || RO_PASSWORD="$(password_for DB_RO_PASSWORD)"

if [[ "$(pg_scalar -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != 1 ]]; then
	pg -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';"
else
	pg -c "ALTER ROLE $DB_USER WITH LOGIN NOSUPERUSER PASSWORD '$DB_PASSWORD';"
fi
[[ "$(pg_scalar -c "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" == 1 ]] ||
	runuser -u postgres -- createdb -O "$DB_USER" -E UTF8 "$DB_NAME"

# Extensions first, as the superuser, in public: the application role cannot create them.
for ext in $EXTENSIONS; do
	pg -d "$DB_NAME" -c "SET search_path = public; CREATE EXTENSION IF NOT EXISTS $ext;" ||
		die "Extension '$ext' could not be created."
	[[ -n "$(pg_scalar -d "$DB_NAME" -c "SELECT extversion FROM pg_extension WHERE extname = '$ext'")" ]] ||
		die "Extension '$ext' is not present after CREATE EXTENSION."
	ok "  $ext $(pg_scalar -d "$DB_NAME" -c "SELECT extversion FROM pg_extension WHERE extname = '$ext'")"
done

pg -d "$DB_NAME" <<EOF
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION $DB_USER;
CREATE SCHEMA IF NOT EXISTS geodata AUTHORIZATION $DB_USER;
ALTER ROLE $DB_USER SET search_path = app, geodata, public;
ALTER DATABASE $DB_NAME SET search_path = app, geodata, public;
EOF

if [[ -n "$DB_RO_USER" ]]; then
	if [[ "$(pg_scalar -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_RO_USER'")" != 1 ]]; then
		pg -c "CREATE ROLE $DB_RO_USER LOGIN PASSWORD '$RO_PASSWORD';"
	else
		pg -c "ALTER ROLE $DB_RO_USER WITH LOGIN NOSUPERUSER PASSWORD '$RO_PASSWORD';"
	fi
	pg -d "$DB_NAME" <<EOF
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_RO_USER;
GRANT USAGE ON SCHEMA app, geodata, public TO $DB_RO_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA app, geodata TO $DB_RO_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE $DB_USER IN SCHEMA app, geodata GRANT SELECT ON TABLES TO $DB_RO_USER;
ALTER ROLE $DB_RO_USER SET search_path = app, geodata, public;
EOF
fi

install -d -m 0750 "$(dirname "$CREDENTIALS_FILE")"
(
	umask 077
	{
		echo "# Written by deploy/provision-postgres.sh. Root only. A later run re-applies these."
		echo "DB_HOST=$LISTEN_ADDR"
		echo "DB_PORT=$PG_PORT"
		echo "DB_NAME=$DB_NAME"
		echo "DB_USER=$DB_USER"
		echo "DB_PASSWORD=$DB_PASSWORD"
		[[ -z "$DB_RO_USER" ]] || echo "DB_RO_USER=$DB_RO_USER"
		[[ -z "$DB_RO_USER" ]] || echo "DB_RO_PASSWORD=$RO_PASSWORD"
	} >"$CREDENTIALS_FILE"
)
chmod 0600 "$CREDENTIALS_FILE"

# ─── Nightly local dump with rotation ───────────────────────────────
log "Installing the nightly dump (tabsira-pg-backup.timer)"
install -d -o postgres -g postgres -m 0750 "$BACKUP_DIR"
cat >/etc/tabsira/postgres-backup.env <<EOF
BACKUP_DIR=$BACKUP_DIR
BACKUP_KEEP_DAYS=$BACKUP_KEEP_DAYS
BACKUP_KEEP_MIN=$BACKUP_KEEP_MIN
DB_NAME=$DB_NAME
PGPORT=$PG_PORT
EOF
cat >/usr/local/bin/tabsira-pg-backup <<'SCRIPT'
#!/usr/bin/env bash
# Nightly dump of the TABSIRA database, installed by deploy/provision-postgres.sh.
# Verified with pg_restore --list, then rotated: older than BACKUP_KEEP_DAYS go,
# except the newest BACKUP_KEEP_MIN.
set -Eeuo pipefail
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$BACKUP_DIR/$DB_NAME-$stamp.dump"
umask 027
pg_dump --format=custom --compress=zstd:3 --file="$dump.part" "$DB_NAME"
pg_restore --list "$dump.part" >/dev/null
mv "$dump.part" "$dump"
pg_dumpall --globals-only --file="$BACKUP_DIR/globals-$stamp.sql"
find "$BACKUP_DIR" -maxdepth 1 -name "$DB_NAME-*.dump" -type f -mtime +"$BACKUP_KEEP_DAYS" | sort |
	awk -v keep="$BACKUP_KEEP_MIN" '{ line[NR] = $0 } END { for (i = 1; i <= NR - keep; i++) print line[i] }' |
	xargs -r rm -f
find "$BACKUP_DIR" -maxdepth 1 -name 'globals-*.sql' -type f -mtime +"$BACKUP_KEEP_DAYS" -delete
echo "wrote $dump ($(du -h "$dump" | cut -f1))"
SCRIPT
chmod 0755 /usr/local/bin/tabsira-pg-backup
cat >/etc/systemd/system/tabsira-pg-backup.service <<'EOF'
[Unit]
Description=Nightly local dump of the TABSIRA database
After=postgresql.service

[Service]
Type=oneshot
User=postgres
Group=postgres
EnvironmentFile=/etc/tabsira/postgres-backup.env
ExecStart=/usr/local/bin/tabsira-pg-backup
Nice=10
IOSchedulingClass=idle
EOF
cat >/etc/systemd/system/tabsira-pg-backup.timer <<'EOF'
[Unit]
Description=Run tabsira-pg-backup nightly

[Timer]
OnCalendar=*-*-* 03:15:00 UTC
RandomizedDelaySec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now tabsira-pg-backup.timer >/dev/null

# ─── Verify ─────────────────────────────────────────────────────────
pg_isready -q -h "$LISTEN_ADDR" -p "$PG_PORT" || die "Nothing answers on $LISTEN_ADDR:$PG_PORT."
# pg_hba admits the application role from the application host only, so a login from
# this host is refused by design. Check what can be checked here; the login itself
# is tested from the application host (docs/OPERATIONS.md, provisioning step 4).
[[ "$(pg_scalar -c "SELECT rolpassword LIKE 'SCRAM-SHA-256\$%' FROM pg_authid WHERE rolname = '$DB_USER'")" == t ]] ||
	die "The password of $DB_USER is not stored as scram-sha-256."
[[ "$(pg_scalar -c "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL")" == 0 ]] ||
	die "pg_hba.conf has errors; see pg_hba_file_rules."
ok "PostgreSQL $PG_VERSION is ready on $LISTEN_ADDR:$PG_PORT"
cat <<EOF

For the application host's environment file (the passwords are also in $CREDENTIALS_FILE):

  DATABASE_URL=postgresql+asyncpg://$DB_USER:<DB_PASSWORD>@$LISTEN_ADDR:$PG_PORT/$DB_NAME
  SYNC_DATABASE_URL=postgresql+psycopg://$DB_USER:<DB_PASSWORD>@$LISTEN_ADDR:$PG_PORT/$DB_NAME

Firewall: run deploy/provision-data.sh to restrict $PG_PORT and Redis to $APP_HOST_VPN_IP.
EOF
