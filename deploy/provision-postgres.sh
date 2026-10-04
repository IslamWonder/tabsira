#!/usr/bin/env bash
#
# provision-postgres.sh — standalone PostgreSQL installer for the production
# database host (db.tabsira.me) on Ubuntu 24.04 LTS (26.04 works too). Native
# packages from the PostgreSQL apt repository (PGDG) and TimescaleDB's, no Docker.
# One file: copy it to the host and run it as root; it needs nothing else from
# the repository.
#
# What it does, in order:
#   1. Adds the PGDG and TimescaleDB repositories and installs PostgreSQL
#      $PG_VERSION (18) with PostGIS, pgvector and TimescaleDB. The cluster is
#      created with PG_LOCALE (en_US.UTF-8). A cluster that already exists with
#      another locale is recreated when every database in it is still empty, and
#      refused otherwise with the manual steps. --check reports which it would be.
#   2. Sets the system timezone to UTC and tunes the kernel for a database host:
#      swappiness, transparent huge pages off, and net.ipv4.ip_nonlocal_bind so a
#      reboot that starts PostgreSQL before Netbird has given its address does not
#      leave the database down.
#   3. Writes a managed tuning file, conf.d/90-tabsira.conf, sized from the host's
#      RAM and CPUs: shared_buffers, work_mem, WAL, parallelism, autovacuum,
#      pg_stat_statements and timescaledb preloaded, slow-query logging, UTC.
#      Rewritten on every run: change the variables below, not the file.
#   4. Listens on loopback and this host's Netbird VPN address (the one on
#      PG_VPN_IFACE, wt0): that is how the application host reaches the database.
#      Never every interface.
#   5. pg_hba.conf gets one managed block: the application role may reach the
#      application database from PG_APP_SUBNET (the VPN network, derived from the
#      wt0 prefix) with scram-sha-256 — or only from APP_HOST_VPN_IP/32 when that
#      is set, which is narrower. No trust lines, never `all all`.
#   6. Creates the application role and database, the four schemas (app and
#      corpus, filled by the app chain; geodata and vectors, one chain each; all
#      migrated by the first deploy), and
#      the nine extensions the API expects, logging each with its version; a
#      missing one is an error. The password is generated on the first run and kept
#      in /etc/tabsira/postgres.env (root only); every later run re-applies it.
#      DB_RO_USER adds a read-only role.
#   7. Installs a nightly local dump (systemd timer, custom format, verified with
#      pg_restore --list, older than PG_BACKUP_KEEP_DAYS pruned but the newest
#      PG_BACKUP_KEEP_MIN always kept).
#   8. Verifies: the cluster answers on the VPN address and the application role
#      can log in over TCP with its password.
#
# It does not touch the host firewall: allow 5432/tcp from the application host in
# the firewall you use. Until then pg_hba.conf is what limits access to 5432.
#
# It ends by printing the DATABASE_URL / SYNC_DATABASE_URL lines for the
# application host's environment file, and the next steps: deploy (which migrates
# the schemas), then deploy/load-data.sh (GeoNames, the corpus archive, vectors).
#
# Re-running is safe and is how you apply a change or pick up a new minor release.
# A new major needs pg_upgradecluster, which this script deliberately does not run.
#
# Settings (environment variables, all optional):
#   PG_VERSION           PostgreSQL major                      (default: 18)
#   PG_VPN_IFACE         Netbird interface                     (default: wt0)
#   PG_LISTEN_ADDR       This host's VPN address (default: the IPv4 on PG_VPN_IFACE,
#                        else the first 100.64.0.0/10 address)
#   PG_APP_SUBNET        CIDR the application host reaches us from (default: the
#                        network of PG_LISTEN_ADDR as the interface declares it)
#   APP_HOST_VPN_IP      The application host's VPN address: pg_hba admits that one
#                        address (/32) instead of the whole subnet (default: none)
#   DB_NAME              Application database                  (default: tabsira)
#   DB_USER              Application role                      (default: tabsira)
#   DB_PASSWORD          Its password (default: read from /etc/tabsira/postgres.env,
#                        generated on the first run)
#   DB_RO_USER           A read-only role, also admitted by pg_hba (default: none)
#   PG_LOCALE            Cluster locale / collation           (default: en_US.UTF-8)
#   PG_MAX_CONNECTIONS   (default: 100)
#   PG_STORAGE           ssd | hdd — sets random_page_cost      (default: ssd)
#   PG_BACKUP            1 | 0 — install the nightly dump timer (default: 1)
#   PG_BACKUP_DIR        (default: /var/backups/tabsira)
#   PG_BACKUP_KEEP_DAYS  (default: 14)
#   PG_BACKUP_KEEP_MIN   (default: 3)
#
# Usage:
#   sudo ./provision-postgres.sh [--check]
#   sudo APP_HOST_VPN_IP=100.73.1.2 ./provision-postgres.sh
#
# Options:
#   --check     Detect, validate and print the plan; change nothing (--dry-run works too)
#   -h, --help
#
set -Eeuo pipefail

# ---------- defaults ----------
PG_VERSION="${PG_VERSION:-18}"
PG_VPN_IFACE="${PG_VPN_IFACE:-${VPN_IFACE:-wt0}}"
PG_LISTEN_ADDR="${PG_LISTEN_ADDR:-${DATA_HOST_VPN_IP:-}}"
PG_APP_SUBNET="${PG_APP_SUBNET:-}"
APP_HOST_VPN_IP="${APP_HOST_VPN_IP:-}"
DB_NAME="${DB_NAME:-tabsira}"
DB_USER="${DB_USER:-tabsira}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_RO_USER="${DB_RO_USER:-}"
PG_LOCALE="${PG_LOCALE:-en_US.UTF-8}"
PG_MAX_CONNECTIONS="${PG_MAX_CONNECTIONS:-100}"
PG_STORAGE="${PG_STORAGE:-ssd}"
PG_BACKUP="${PG_BACKUP:-1}"
PG_BACKUP_DIR="${PG_BACKUP_DIR:-/var/backups/tabsira}"
PG_BACKUP_KEEP_DAYS="${PG_BACKUP_KEEP_DAYS:-14}"
PG_BACKUP_KEEP_MIN="${PG_BACKUP_KEEP_MIN:-3}"
PG_PORT=5432

CREDENTIALS_FILE=/etc/tabsira/postgres.env
CHECK_ONLY=0
# What the API needs, and why. Created in public, as the superuser: the application
# role cannot create them, and putting them in `app` breaks tools that empty that schema.
EXTENSIONS=(
	"postgis:places, approximate locations and the geodata schema"
	"vector:the scripture embeddings (pgvector)"
	"timescaledb:the audit log and the time series (hypertables)"
	"pg_trgm:trigram indexes for fuzzy search"
	"unaccent:accent-insensitive search"
	"pgcrypto:gen_random_uuid() and digests"
	"btree_gin:composite GIN indexes"
	"btree_gist:exclusion constraints and mixed GiST indexes"
	"pg_stat_statements:query statistics"
)

# ---------- helpers ----------
if [[ -t 1 ]]; then
	C_RESET=$'\e[0m' C_BOLD=$'\e[1m' C_RED=$'\e[31m' C_GREEN=$'\e[32m' C_YELLOW=$'\e[33m' C_BLUE=$'\e[34m'
else
	C_RESET="" C_BOLD="" C_RED="" C_GREEN="" C_YELLOW="" C_BLUE=""
fi
log() { printf '%s[tabsira]%s %s\n' "${C_BLUE}${C_BOLD}" "$C_RESET" "$*"; }
ok() { printf '%s[ ok ]%s %s\n' "${C_GREEN}${C_BOLD}" "$C_RESET" "$*"; }
warn() { printf '%s[warn]%s %s\n' "${C_YELLOW}${C_BOLD}" "$C_RESET" "$*" >&2; }
die() {
	printf '%s[err ]%s %s\n' "${C_RED}${C_BOLD}" "$C_RESET" "$*" >&2
	exit 1
}
usage() {
	sed -n '2,/^set -Eeuo/p' "$0" | sed '$d; s/^# \{0,1\}//'
	exit 0
}

# psql as the cluster superuser, quiet and fatal on error.
pg() { runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q "$@"; }
pg_scalar() { runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -tA "$@"; }

# Relations in database $1 not owned by an extension and not in the system
# schemas: zero means only this installer has touched it.
db_user_relations() {
	pg_scalar -d "$1" -c "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
		WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
		AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
		AND n.nspname NOT LIKE '\\_timescaledb%' AND n.nspname NOT IN ('timescaledb_information', 'timescaledb_experimental', 'toolkit_experimental')
		AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')"
}

# The running cluster's encoding and collation, or nothing when there is none.
cluster_locale() {
	pg_lsclusters -h 2>/dev/null | awk -v v="$PG_VERSION" '$1 == v && $2 == "main" && $4 == "online"' | grep -q . || return 0
	pg_scalar -c "SELECT pg_encoding_to_char(encoding) || '/' || datcollate FROM pg_database WHERE datname = 'template1'" 2>/dev/null || true
}

# Databases, other than the templates and postgres, holding anything this
# installer did not create. Empty output means the cluster can be recreated.
populated_databases() {
	local db
	while read -r db; do
		[[ -n $db ]] || continue
		[[ "$(db_user_relations "$db")" == 0 ]] || printf '%s\n' "$db"
	done < <(pg_scalar -c "SELECT datname FROM pg_database WHERE datname NOT IN ('postgres', 'template0', 'template1') ORDER BY 1")
}

is_ipv4() { [[ $1 =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }
is_cidr() { [[ $1 =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]; }

# Is IPv4 address $1 inside CIDR $2?
in_cidr() {
	local ip="$1" net="${2%/*}" bits="${2#*/}" a b c d
	IFS=. read -r a b c d <<<"$ip"
	local ipn=$(((a << 24) + (b << 16) + (c << 8) + d))
	IFS=. read -r a b c d <<<"$net"
	local netn=$(((a << 24) + (b << 16) + (c << 8) + d))
	local mask=$(((0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF))
	[[ $bits -eq 0 ]] && mask=0
	[[ $((ipn & mask)) -eq $((netn & mask)) ]]
}

iface_addr() { ip -4 -o addr show dev "$1" scope global 2>/dev/null | awk 'NR == 1 { print $4 }'; }
prefix_of() { ip -4 -o addr show scope global 2>/dev/null | awk -v a="$1" '{ split($4, p, "/"); if (p[1] == a) { print p[2]; exit } }'; }

# The network of a.b.c.d/nn as a CIDR, e.g. 100.73.65.124/16 -> 100.73.0.0/16.
network_of() {
	local ip="${1%/*}" bits="${1#*/}" a b c d n mask
	IFS=. read -r a b c d <<<"$ip"
	n=$(((a << 24) + (b << 16) + (c << 8) + d))
	mask=$(((0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF))
	[[ $bits -eq 0 ]] && mask=0
	n=$((n & mask))
	printf '%d.%d.%d.%d/%d' $((n >> 24 & 255)) $((n >> 16 & 255)) $((n >> 8 & 255)) $((n & 255)) "$bits"
}

# First global IPv4 on the host in the CGNAT range Netbird hands out.
detect_vpn_addr() {
	local a
	while read -r a; do
		case "$a" in
		100.6[4-9].* | 100.[7-9][0-9].* | 100.1[01][0-9].* | 100.12[0-7].*)
			printf '%s' "$a"
			return 0
			;;
		esac
	done < <(ip -4 -o addr show scope global 2>/dev/null | awk '{ print $4 }' | cut -d/ -f1)
	return 1
}

# A password from the environment, else the credentials file, else made now.
password_for() {
	local key="$1" value="${2:-}"
	[[ -n $value || ! -r $CREDENTIALS_FILE ]] || value="$(sed -n "s/^${key}=//p" "$CREDENTIALS_FILE" | tail -n1)"
	[[ -n $value ]] || value="$(openssl rand -hex 24)"
	[[ $value =~ ^[A-Za-z0-9._~-]+$ ]] || die "$key may only contain letters, digits and . _ ~ - so it can sit in a URL unescaped."
	printf '%s' "$value"
}

# ---------- arguments ----------
for arg in "$@"; do
	case "$arg" in
	--check | --dry-run) CHECK_ONLY=1 ;;
	-h | --help) usage ;;
	*) die "Unknown option: $arg (see --help)" ;;
	esac
done

# ---------- host checks ----------
[[ $EUID -eq 0 ]] || die "Run with sudo."
command -v ip >/dev/null || die "iproute2 is required (apt-get install iproute2)."
command -v openssl >/dev/null || die "openssl is required to generate a password."
[[ -r /etc/os-release ]] || die "Cannot read /etc/os-release."
# shellcheck disable=SC1091
. /etc/os-release
[[ ${ID:-} == ubuntu ]] || die "This installer targets Ubuntu (got: ${ID:-unknown})."
CODENAME="${VERSION_CODENAME:?no VERSION_CODENAME in /etc/os-release}"
case "${VERSION_ID:-}" in
24.04 | 26.04) ;;
*) warn "Written for Ubuntu 24.04 / 26.04; this is ${VERSION_ID:-unknown}." ;;
esac
log "Ubuntu ${VERSION_ID:-?} ($CODENAME), PostgreSQL $PG_VERSION"

[[ $PG_VERSION =~ ^[0-9]+$ ]] || die "PG_VERSION must be a major version number (got '$PG_VERSION')."
[[ $PG_MAX_CONNECTIONS =~ ^[0-9]+$ ]] || die "PG_MAX_CONNECTIONS must be a number."
[[ $PG_LOCALE =~ ^[A-Za-z_]+\.UTF-8$ ]] || die "PG_LOCALE must be a UTF-8 locale such as en_US.UTF-8 (got '$PG_LOCALE')."
[[ $PG_BACKUP_KEEP_DAYS =~ ^[0-9]+$ && $PG_BACKUP_KEEP_MIN =~ ^[0-9]+$ ]] || die "PG_BACKUP_KEEP_DAYS and PG_BACKUP_KEEP_MIN must be numbers."
case "$PG_STORAGE" in ssd | hdd) ;; *) die "PG_STORAGE must be ssd or hdd." ;; esac
[[ $DB_NAME =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_NAME must be a plain identifier (got '$DB_NAME')."
[[ $DB_USER =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_USER must be a plain identifier (got '$DB_USER')."
[[ -z $DB_RO_USER || $DB_RO_USER =~ ^[a-z_][a-z0-9_]*$ ]] || die "DB_RO_USER must be a plain identifier (got '$DB_RO_USER')."

# ---------- addresses ----------
if [[ -z $PG_LISTEN_ADDR ]]; then
	VPN_CIDR="$(iface_addr "$PG_VPN_IFACE")"
	if [[ -n $VPN_CIDR ]]; then
		PG_LISTEN_ADDR="${VPN_CIDR%/*}"
	else
		PG_LISTEN_ADDR="$(detect_vpn_addr)" ||
			die "No address on $PG_VPN_IFACE and no 100.64.0.0/10 address on this host. Is Netbird up? Otherwise set PG_LISTEN_ADDR."
		warn "$PG_VPN_IFACE has no address; using $PG_LISTEN_ADDR from the CGNAT range instead."
	fi
fi
case "$PG_LISTEN_ADDR" in
'*' | 0.0.0.0 | '::' | '') die "Refusing to bind a production database to every interface." ;;
esac
LISTEN_PREFIX="$(prefix_of "$PG_LISTEN_ADDR")"
[[ -n $LISTEN_PREFIX ]] || die "PG_LISTEN_ADDR=$PG_LISTEN_ADDR is not an address of this host."
LISTEN_IFACE="$(ip -4 -o addr show scope global | awk -v a="$PG_LISTEN_ADDR" '{ split($4, p, "/"); if (p[1] == a) { print $2; exit } }')"
if [[ -z $PG_APP_SUBNET ]]; then
	PG_APP_SUBNET="$(network_of "$PG_LISTEN_ADDR/$LISTEN_PREFIX")"
fi
is_cidr "$PG_APP_SUBNET" || die "PG_APP_SUBNET must be an IPv4 CIDR such as 100.73.0.0/16 (got '$PG_APP_SUBNET')."
[[ ${PG_APP_SUBNET##*/} -ge 8 ]] || die "Refusing PG_APP_SUBNET=$PG_APP_SUBNET; name the network the application host reaches us from."
HBA_SOURCE="$PG_APP_SUBNET"
if [[ -n $APP_HOST_VPN_IP ]]; then
	is_ipv4 "$APP_HOST_VPN_IP" || die "APP_HOST_VPN_IP must be one IPv4 address (got '$APP_HOST_VPN_IP')."
	HBA_SOURCE="$APP_HOST_VPN_IP/32"
fi
LISTEN="localhost,$PG_LISTEN_ADDR"

# ---------- credentials ----------
if [[ -n $DB_PASSWORD ]]; then
	PASSWORD_SOURCE="from the environment"
elif [[ -r $CREDENTIALS_FILE ]] && grep -q '^DB_PASSWORD=' "$CREDENTIALS_FILE"; then
	PASSWORD_SOURCE="from $CREDENTIALS_FILE"
else
	PASSWORD_SOURCE="generated now"
fi
DB_PASSWORD="$(password_for DB_PASSWORD "$DB_PASSWORD")"
RO_PASSWORD=""
[[ -z $DB_RO_USER ]] || RO_PASSWORD="$(password_for DB_RO_PASSWORD "${DB_RO_PASSWORD:-}")"

# ---------- tuning, sized from the host ----------
MEM_KB="$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)"
MEM_MB=$((MEM_KB / 1024))
CPUS="$(nproc)"
[[ $MEM_MB -ge 1024 ]] || warn "Only ${MEM_MB} MB of RAM; PostgreSQL will run but the sizing below is for 2 GB and up."
SHARED_BUFFERS_MB=$((MEM_MB / 4))
EFFECTIVE_CACHE_MB=$((MEM_MB * 3 / 4))
MAINT_WORK_MEM_MB=$((MEM_MB / 16))
[[ $MAINT_WORK_MEM_MB -gt 2048 ]] && MAINT_WORK_MEM_MB=2048
[[ $MAINT_WORK_MEM_MB -lt 64 ]] && MAINT_WORK_MEM_MB=64
WORK_MEM_KB=$(((MEM_KB - SHARED_BUFFERS_MB * 1024) / (PG_MAX_CONNECTIONS * 3)))
[[ $WORK_MEM_KB -lt 4096 ]] && WORK_MEM_KB=4096
[[ $WORK_MEM_KB -gt 65536 ]] && WORK_MEM_KB=65536
WAL_BUFFERS_MB=16
[[ $SHARED_BUFFERS_MB -lt 512 ]] && WAL_BUFFERS_MB=$((SHARED_BUFFERS_MB / 32 > 0 ? SHARED_BUFFERS_MB / 32 : 1))
MAX_WAL_MB=4096
[[ $MEM_MB -lt 4096 ]] && MAX_WAL_MB=2048
AUTOVACUUM_WORKERS=3
AUTOVACUUM_WORK_MEM_MB=$((MEM_MB / 32))
[[ $AUTOVACUUM_WORK_MEM_MB -gt 1024 ]] && AUTOVACUUM_WORK_MEM_MB=1024
[[ $AUTOVACUUM_WORK_MEM_MB -lt 32 ]] && AUTOVACUUM_WORK_MEM_MB=32
AUTOVACUUM_COST_LIMIT=1000
PARALLEL_PER_GATHER=$((CPUS / 2))
[[ $PARALLEL_PER_GATHER -lt 1 ]] && PARALLEL_PER_GATHER=1
[[ $PARALLEL_PER_GATHER -gt 4 ]] && PARALLEL_PER_GATHER=4
# TimescaleDB runs its own background workers (policies, compression).
TS_WORKERS=$((CPUS + 2))
[[ $TS_WORKERS -lt 4 ]] && TS_WORKERS=4
MAX_WORKERS=$((CPUS + TS_WORKERS + 2))
RANDOM_PAGE_COST=1.1
IO_CONCURRENCY=200
if [[ $PG_STORAGE == hdd ]]; then
	RANDOM_PAGE_COST=4
	IO_CONCURRENCY=2
	AUTOVACUUM_COST_LIMIT=200
fi

PG_CONF_DIR="/etc/postgresql/$PG_VERSION/main"
TUNING_FILE="$PG_CONF_DIR/conf.d/90-tabsira.conf"
HBA_FILE="$PG_CONF_DIR/pg_hba.conf"

cat <<EOF

  PostgreSQL     $PG_VERSION from apt.postgresql.org ($CODENAME-pgdg), PostGIS, pgvector, TimescaleDB
  Listen on      $LISTEN (port $PG_PORT, or the cluster's own if another cluster holds it)
  Address        $PG_LISTEN_ADDR/$LISTEN_PREFIX on $LISTEN_IFACE$([[ $LISTEN_IFACE == "$PG_VPN_IFACE" ]] && echo " (Netbird VPN)")
  pg_hba         host $DB_NAME $DB_USER $HBA_SOURCE scram-sha-256
EOF
[[ -z $DB_RO_USER ]] || echo "                 host $DB_NAME $DB_RO_USER $HBA_SOURCE scram-sha-256"
cat <<EOF
  Database       $DB_NAME, owned by $DB_USER (password $PASSWORD_SOURCE)${DB_RO_USER:+; read-only role $DB_RO_USER}
  Schemas        app, corpus, geodata, vectors (search_path app, corpus, geodata, vectors, public)
  Extensions     $(printf '%s ' "${EXTENSIONS[@]%%:*}")
  Locale         UTF8/$PG_LOCALE$(
	current="$(cluster_locale)"
	if [[ -z $current ]]; then
		echo " (no running cluster $PG_VERSION/main yet: it will be created with this locale)"
	elif [[ ${current/utf8/UTF-8} == "UTF8/$PG_LOCALE" ]]; then
		echo " (cluster $PG_VERSION/main already is)"
	else
		populated="$(populated_databases | tr '\n' ' ')"
		if [[ -z $populated ]]; then
			echo " (cluster $PG_VERSION/main is $current and holds no data: it will be recreated)"
		else
			echo " (cluster $PG_VERSION/main is $current and holds data in: ${populated% }: the run will refuse)"
		fi
	fi
)
  Credentials    $CREDENTIALS_FILE (root only)
  Host           ${MEM_MB} MB RAM, $CPUS CPU(s), $PG_STORAGE storage
  Tuning         shared_buffers=${SHARED_BUFFERS_MB}MB  effective_cache_size=${EFFECTIVE_CACHE_MB}MB
                 work_mem=${WORK_MEM_KB}kB  maintenance_work_mem=${MAINT_WORK_MEM_MB}MB
                 max_connections=$PG_MAX_CONNECTIONS  max_wal_size=${MAX_WAL_MB}MB
                 max_parallel_workers_per_gather=$PARALLEL_PER_GATHER  random_page_cost=$RANDOM_PAGE_COST
  Backups        $([[ $PG_BACKUP == 1 ]] && echo "nightly to $PG_BACKUP_DIR, $PG_BACKUP_KEEP_DAYS days, newest $PG_BACKUP_KEEP_MIN always kept" || echo "off (PG_BACKUP=0)")
  Firewall       not managed here; allow $PG_PORT/tcp from the application host

EOF

if ((CHECK_ONLY)); then
	ok "--check: nothing changed."
	exit 0
fi

# ---------- packages ----------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg openssl >/dev/null
install -m 0755 -d /etc/apt/keyrings

KEYRING=/etc/apt/keyrings/postgresql.gpg
if [[ ! -s $KEYRING ]]; then
	log "Adding the PGDG signing key"
	curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o "$KEYRING"
	chmod a+r "$KEYRING"
fi
curl -fsSIo /dev/null "https://apt.postgresql.org/pub/repos/apt/dists/${CODENAME}-pgdg/Release" ||
	die "apt.postgresql.org has no '${CODENAME}-pgdg' suite yet; PostgreSQL cannot be installed from PGDG on this release."
PGDG_LIST=/etc/apt/sources.list.d/pgdg.list
PGDG_LINE="deb [signed-by=$KEYRING] https://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main"
if [[ ! -f $PGDG_LIST ]] || ! grep -qxF "$PGDG_LINE" "$PGDG_LIST"; then
	log "Adding the PGDG apt repository for $CODENAME"
	echo "$PGDG_LINE" >"$PGDG_LIST"
fi

TS_KEYRING=/etc/apt/keyrings/timescaledb.gpg
if [[ ! -s $TS_KEYRING ]]; then
	log "Adding the TimescaleDB signing key"
	curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o "$TS_KEYRING"
	chmod a+r "$TS_KEYRING"
fi
TS_LIST=/etc/apt/sources.list.d/timescaledb.list
TS_LINE="deb [signed-by=$TS_KEYRING] https://packagecloud.io/timescale/timescaledb/ubuntu/ ${CODENAME} main"
if [[ ! -f $TS_LIST ]] || ! grep -qxF "$TS_LINE" "$TS_LIST"; then
	log "Adding the TimescaleDB apt repository for $CODENAME"
	echo "$TS_LINE" >"$TS_LIST"
fi
apt-get update -qq

# The cluster the package creates takes its locale from the environment, and an
# Ubuntu cloud image says C.UTF-8. Generate PG_LOCALE and install under it.
if ! locale -a 2>/dev/null | grep -qix "${PG_LOCALE/UTF-8/utf8}"; then
	log "Generating locale $PG_LOCALE"
	apt-get install -y -qq locales >/dev/null
	grep -qxF "$PG_LOCALE UTF-8" /etc/locale.gen 2>/dev/null || echo "$PG_LOCALE UTF-8" >>/etc/locale.gen
	locale-gen "$PG_LOCALE" >/dev/null
fi

log "Installing PostgreSQL $PG_VERSION, PostGIS, pgvector and TimescaleDB"
LANG="$PG_LOCALE" LC_ALL="$PG_LOCALE" apt-get install -y -qq \
	"postgresql-$PG_VERSION" \
	"postgresql-client-$PG_VERSION" \
	"postgresql-$PG_VERSION-postgis-3" \
	"postgresql-$PG_VERSION-postgis-3-scripts" \
	"postgresql-$PG_VERSION-pgvector" \
	"timescaledb-2-postgresql-$PG_VERSION" >/dev/null
INSTALLED="$(dpkg-query -W -f='${Version}' "postgresql-$PG_VERSION")"
ok "postgresql-$PG_VERSION $INSTALLED"

wait_for_cluster() {
	local _
	for _ in $(seq 1 30); do
		pg_isready -q -p "$PG_PORT" && return 0
		sleep 1
	done
	return 1
}
if ! pg_lsclusters -h | awk '{ print $1 "/" $2 }' | grep -qx "$PG_VERSION/main"; then
	log "Creating cluster $PG_VERSION/main with locale $PG_LOCALE"
	pg_createcluster --locale "$PG_LOCALE" "$PG_VERSION" main
fi
# The port is the cluster's: postgresql-common gives 5432 to the first cluster on
# the host and 5433+ to the next, so never assume it.
PG_PORT="$(pg_lsclusters -h | awk -v v="$PG_VERSION" '$1 == v && $2 == "main" { print $3 }')"
[[ $PG_PORT =~ ^[0-9]+$ ]] || die "Could not read the port of cluster $PG_VERSION/main from pg_lsclusters."
[[ $PG_PORT == 5432 ]] || warn "Cluster $PG_VERSION/main listens on $PG_PORT, not 5432: another cluster owns 5432 on this host."
pg_ctlcluster "$PG_VERSION" main start >/dev/null 2>&1 || true
wait_for_cluster || die "Cluster $PG_VERSION/main did not start; see journalctl -u postgresql@$PG_VERSION-main."

# A cluster with the wrong locale or encoding cannot be fixed in place: the
# collation is baked into every index. Recreate it while it is still empty.
CLUSTER_ENCODING="$(pg_scalar -c "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = 'template1'")"
CLUSTER_COLLATE="$(pg_scalar -c "SELECT datcollate FROM pg_database WHERE datname = 'template1'")"
if [[ $CLUSTER_ENCODING != UTF8 || ${CLUSTER_COLLATE/utf8/UTF-8} != "$PG_LOCALE" ]]; then
	POPULATED="$(populated_databases | tr '\n' ' ')"
	if [[ -n $POPULATED ]]; then
		die "Cluster $PG_VERSION/main is $CLUSTER_ENCODING/$CLUSTER_COLLATE, not UTF8/$PG_LOCALE, and holds data in: ${POPULATED% }. Dump it, then: pg_dropcluster --stop $PG_VERSION main && pg_createcluster --locale $PG_LOCALE $PG_VERSION main, and re-run this installer before restoring."
	fi
	warn "Cluster $PG_VERSION/main is $CLUSTER_ENCODING/$CLUSTER_COLLATE and holds no data; recreating it as UTF8/$PG_LOCALE"
	pg_dropcluster --stop "$PG_VERSION" main
	pg_createcluster --locale "$PG_LOCALE" "$PG_VERSION" main
	pg_ctlcluster "$PG_VERSION" main start
	wait_for_cluster || die "The recreated cluster did not start."
	CLUSTER_COLLATE="$(pg_scalar -c "SELECT datcollate FROM pg_database WHERE datname = 'template1'")"
fi
ok "Cluster $PG_VERSION/main: UTF8, $CLUSTER_COLLATE"

# ---------- time ----------
if [[ "$(timedatectl show -p Timezone --value 2>/dev/null || true)" != UTC ]]; then
	log "Setting the system timezone to UTC"
	timedatectl set-timezone UTC 2>/dev/null || {
		ln -sf /usr/share/zoneinfo/UTC /etc/localtime
		echo UTC >/etc/timezone
	}
fi

# ---------- kernel ----------
log "Kernel settings for a database host"
cat >/etc/sysctl.d/90-tabsira-postgres.conf <<'EOF'
# Written by deploy/provision-postgres.sh
# Keep PostgreSQL's shared buffers in RAM; swap only under real pressure.
vm.swappiness = 10
# Netbird adds its address a little after boot; PostgreSQL listens on it by name.
net.ipv4.ip_nonlocal_bind = 1
EOF
sysctl -q --system >/dev/null 2>&1 || warn "Some sysctl keys could not be applied (fine inside a container, not on a VM)."

cat >/etc/systemd/system/tabsira-disable-thp.service <<'EOF'
[Unit]
Description=Disable transparent huge pages (TABSIRA data store)
DefaultDependencies=no
After=sysinit.target local-fs.target
Before=postgresql.service redis-server.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled'
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/defrag'
RemainAfterExit=yes

[Install]
WantedBy=basic.target
EOF
# Start PostgreSQL after Netbird when the VPN client is installed (ordering only).
install -d "/etc/systemd/system/postgresql@.service.d"
cat >"/etc/systemd/system/postgresql@.service.d/tabsira-netbird.conf" <<'EOF'
# Written by deploy/provision-postgres.sh
[Unit]
After=netbird.service
EOF
systemctl daemon-reload
systemctl enable --now tabsira-disable-thp.service >/dev/null 2>&1 || warn "Could not disable transparent huge pages (not a fatal problem)."

# ---------- postgresql.conf (managed include) ----------
grep -qE "^\s*include_dir\s*=\s*'conf.d'" "$PG_CONF_DIR/postgresql.conf" ||
	echo "include_dir = 'conf.d'" >>"$PG_CONF_DIR/postgresql.conf"
install -d -o postgres -g postgres -m 0755 "$PG_CONF_DIR/conf.d"

log "Writing $TUNING_FILE"
cat >"$TUNING_FILE" <<EOF
# Managed by deploy/provision-postgres.sh — rewritten on every run.
# Sized for ${MEM_MB} MB RAM, $CPUS CPU(s), $PG_STORAGE storage. Change the
# variables the script reads and re-run it rather than editing this file.

# --- network ---
listen_addresses = '$LISTEN'
max_connections = $PG_MAX_CONNECTIONS
password_encryption = scram-sha-256

# --- memory ---
shared_buffers = ${SHARED_BUFFERS_MB}MB
effective_cache_size = ${EFFECTIVE_CACHE_MB}MB
work_mem = ${WORK_MEM_KB}kB
maintenance_work_mem = ${MAINT_WORK_MEM_MB}MB
huge_pages = try

# --- WAL and checkpoints ---
wal_buffers = ${WAL_BUFFERS_MB}MB
min_wal_size = 1GB
max_wal_size = ${MAX_WAL_MB}MB
checkpoint_completion_target = 0.9
checkpoint_timeout = 15min
wal_compression = zstd

# --- planner and I/O ---
random_page_cost = $RANDOM_PAGE_COST
effective_io_concurrency = $IO_CONCURRENCY
default_statistics_target = 100
max_worker_processes = $MAX_WORKERS
max_parallel_workers = $CPUS
max_parallel_workers_per_gather = $PARALLEL_PER_GATHER
max_parallel_maintenance_workers = $PARALLEL_PER_GATHER

# --- autovacuum ---
autovacuum_max_workers = $AUTOVACUUM_WORKERS
autovacuum_work_mem = ${AUTOVACUUM_WORK_MEM_MB}MB
autovacuum_vacuum_cost_limit = $AUTOVACUUM_COST_LIMIT
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.02

# --- sessions ---
idle_in_transaction_session_timeout = 10min
tcp_keepalives_idle = 60
tcp_keepalives_interval = 10
tcp_keepalives_count = 6

# --- extensions loaded at start ---
shared_preload_libraries = 'pg_stat_statements,timescaledb'
timescaledb.max_background_workers = $TS_WORKERS
timescaledb.telemetry_level = off
pg_stat_statements.track = all
pg_stat_statements.max = 10000

# --- observability ---
track_io_timing = on
log_min_duration_statement = 500
log_checkpoints = on
log_lock_waits = on
log_temp_files = 10MB
log_autovacuum_min_duration = 1s
log_line_prefix = '%m [%p] %q%u@%d %a '

# --- time ---
timezone = 'UTC'
log_timezone = 'UTC'
EOF
chown postgres:postgres "$TUNING_FILE"
chmod 0644 "$TUNING_FILE"

# conf.d is read in name order and the last value wins: a file sorting after this
# one silently overrides what was sized above.
for other in "$PG_CONF_DIR"/conf.d/*.conf; do
	[[ -f $other && $other != "$TUNING_FILE" && $(basename "$other") > $(basename "$TUNING_FILE") ]] || continue
	overridden="$(grep -oE '^[[:space:]]*[a-z_.]+[[:space:]]*=' "$other" | tr -d ' =' |
		grep -Fxf <(grep -oE '^[a-z_.]+[[:space:]]*=' "$TUNING_FILE" | tr -d ' =') | paste -sd ' ' || true)"
	[[ -n $overridden ]] &&
		warn "$other loads after $(basename "$TUNING_FILE") and overrides: $overridden. Move it out of conf.d unless that is intended."
done

# ---------- pg_hba.conf (managed block) ----------
log "Writing the managed block in $HBA_FILE"
HBA_BEGIN="# BEGIN tabsira (managed by deploy/provision-postgres.sh)"
HBA_END="# END tabsira"
HBA_TMP="$(mktemp)"
awk -v b="$HBA_BEGIN" -v e="$HBA_END" '
	$0 == b { skip = 1; next }
	$0 == e { skip = 0; next }
	skip { next }
	/^host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1\/32[[:space:]]+trust/ { next }
	{ print }
' "$HBA_FILE" >"$HBA_TMP"
{
	echo
	echo "$HBA_BEGIN"
	printf 'host\t%s\t%s\t%s\tscram-sha-256\n' "$DB_NAME" "$DB_USER" "$HBA_SOURCE"
	[[ -z $DB_RO_USER ]] || printf 'host\t%s\t%s\t%s\tscram-sha-256\n' "$DB_NAME" "$DB_RO_USER" "$HBA_SOURCE"
	# The login check below connects from this host's own VPN address.
	if [[ $HBA_SOURCE == */32 ]]; then
		printf 'host\t%s\t%s\t%s/32\tscram-sha-256\n' "$DB_NAME" "$DB_USER" "$PG_LISTEN_ADDR"
	fi
	echo "$HBA_END"
} >>"$HBA_TMP"
install -o postgres -g postgres -m 0640 "$HBA_TMP" "$HBA_FILE"
rm -f "$HBA_TMP"

# ---------- restart and wait ----------
log "Restarting postgresql@$PG_VERSION-main"
systemctl enable --now postgresql >/dev/null 2>&1 || true
systemctl restart "postgresql@$PG_VERSION-main"
wait_for_cluster || {
	journalctl -u "postgresql@$PG_VERSION-main" -n 30 --no-pager >&2 || true
	die "PostgreSQL did not come back after the restart; see the log above and $PG_CONF_DIR."
}
ok "PostgreSQL is up: $(pg_scalar -c 'SHOW server_version;')"

# ---------- role, database, schemas, extensions ----------
log "Ensuring role '$DB_USER' with its password"
if [[ "$(pg_scalar -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'")" != 1 ]]; then
	pg -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';"
else
	pg -c "ALTER ROLE $DB_USER WITH LOGIN NOSUPERUSER PASSWORD '$DB_PASSWORD';"
fi

log "Ensuring database '$DB_NAME'"
if [[ "$(pg_scalar -c "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" != 1 ]]; then
	runuser -u postgres -- createdb -O "$DB_USER" -E UTF8 "$DB_NAME"
fi

log "Extensions in '$DB_NAME'"
for entry in "${EXTENSIONS[@]}"; do
	ext="${entry%%:*}"
	why="${entry#*:}"
	pg -d "$DB_NAME" -c "SET search_path = public; CREATE EXTENSION IF NOT EXISTS $ext;" ||
		die "Extension '$ext' could not be created ($why)."
	ext_version="$(pg_scalar -d "$DB_NAME" -c "SELECT extversion FROM pg_extension WHERE extname = '$ext'")"
	[[ -n $ext_version ]] || die "Extension '$ext' is not present after CREATE EXTENSION."
	ok "  $ext $ext_version — $why"
done

log "Schemas (app, corpus, geodata, vectors; search_path app, corpus, geodata, vectors, public)"
pg -d "$DB_NAME" <<EOF
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION $DB_USER;
CREATE SCHEMA IF NOT EXISTS corpus AUTHORIZATION $DB_USER;
CREATE SCHEMA IF NOT EXISTS geodata AUTHORIZATION $DB_USER;
CREATE SCHEMA IF NOT EXISTS vectors AUTHORIZATION $DB_USER;
ALTER ROLE $DB_USER SET search_path = app, corpus, geodata, vectors, public;
ALTER DATABASE $DB_NAME SET search_path = app, corpus, geodata, vectors, public;
EOF

if [[ -n $DB_RO_USER ]]; then
	log "Ensuring read-only role '$DB_RO_USER'"
	if [[ "$(pg_scalar -c "SELECT 1 FROM pg_roles WHERE rolname = '$DB_RO_USER'")" != 1 ]]; then
		pg -c "CREATE ROLE $DB_RO_USER LOGIN PASSWORD '$RO_PASSWORD';"
	else
		pg -c "ALTER ROLE $DB_RO_USER WITH LOGIN NOSUPERUSER PASSWORD '$RO_PASSWORD';"
	fi
	pg -d "$DB_NAME" <<EOF
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_RO_USER;
GRANT USAGE ON SCHEMA app, corpus, geodata, vectors, public TO $DB_RO_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA app, corpus, geodata, vectors TO $DB_RO_USER;
ALTER DEFAULT PRIVILEGES FOR ROLE $DB_USER IN SCHEMA app, corpus, geodata, vectors GRANT SELECT ON TABLES TO $DB_RO_USER;
ALTER ROLE $DB_RO_USER SET search_path = app, corpus, geodata, vectors, public;
EOF
fi
ok "Database '$DB_NAME' ready: ${#EXTENSIONS[@]} extensions, four schemas, PostGIS $(pg_scalar -d "$DB_NAME" -c 'SELECT PostGIS_Lib_Version();')"

# ---------- credentials file ----------
install -d -m 0750 /etc/tabsira
umask 077
cat >"$CREDENTIALS_FILE" <<EOF
# Written by deploy/provision-postgres.sh. Root only.
# Re-running the installer re-applies DB_PASSWORD to the role, so change it here
# and re-run rather than with ALTER ROLE.
DB_HOST=$PG_LISTEN_ADDR
DB_PORT=$PG_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
EOF
[[ -z $DB_RO_USER ]] || printf 'DB_RO_USER=%s\nDB_RO_PASSWORD=%s\n' "$DB_RO_USER" "$RO_PASSWORD" >>"$CREDENTIALS_FILE"
umask 022
chmod 0600 "$CREDENTIALS_FILE"

# ---------- nightly local dump ----------
if [[ $PG_BACKUP == 1 ]]; then
	log "Installing the nightly dump timer (tabsira-pg-backup.timer)"
	install -d -o postgres -g postgres -m 0750 "$PG_BACKUP_DIR"
	cat >/etc/tabsira/postgres-backup.env <<EOF
# Read by tabsira-pg-backup.service. No secrets: pg_dump runs as postgres over the socket.
BACKUP_DIR=$PG_BACKUP_DIR
BACKUP_KEEP_DAYS=$PG_BACKUP_KEEP_DAYS
BACKUP_KEEP_MIN=$PG_BACKUP_KEEP_MIN
DB_NAME=$DB_NAME
PGPORT=$PG_PORT
EOF
	chmod 0644 /etc/tabsira/postgres-backup.env
	cat >/usr/local/bin/tabsira-pg-backup <<'EOF'
#!/usr/bin/env bash
# Nightly local dump of the TABSIRA database, installed by deploy/provision-postgres.sh;
# settings in /etc/tabsira/postgres-backup.env. Verified with pg_restore --list, then
# rotated: older than BACKUP_KEEP_DAYS go, except the newest BACKUP_KEEP_MIN.
set -Eeuo pipefail
BACKUP_DIR="${BACKUP_DIR:-/var/backups/tabsira}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
BACKUP_KEEP_MIN="${BACKUP_KEEP_MIN:-3}"
DB_NAME="${DB_NAME:-tabsira}"
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
EOF
	chmod 0755 /usr/local/bin/tabsira-pg-backup
	cat >/etc/systemd/system/tabsira-pg-backup.service <<'EOF'
[Unit]
Description=Nightly local dump of the TABSIRA database
After=postgresql.service
Requires=postgresql.service

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
	ok "Dumps land in $PG_BACKUP_DIR at 03:15 UTC; run one now with: systemctl start tabsira-pg-backup.service"
fi

# ---------- verify ----------
log "Verifying the VPN listener and the application login"
pg_isready -q -h "$PG_LISTEN_ADDR" -p "$PG_PORT" || die "Nothing answers on $PG_LISTEN_ADDR:$PG_PORT."
# Connecting to our own VPN address comes from that address, so this goes through
# the managed pg_hba block, as the application host will.
if [[ $HBA_SOURCE == */32 ]] || in_cidr "$PG_LISTEN_ADDR" "$PG_APP_SUBNET"; then
	PGPASSWORD="$DB_PASSWORD" psql -X -q -h "$PG_LISTEN_ADDR" -p "$PG_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc 'SELECT 1' >/dev/null ||
		die "The application role cannot log in over TCP on $PG_LISTEN_ADDR; check $HBA_FILE."
else
	warn "$PG_LISTEN_ADDR is outside $PG_APP_SUBNET, so the rule can only be proven from the application host."
fi
[[ "$(pg_scalar -c "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL")" == 0 ]] ||
	die "pg_hba.conf has errors; see pg_hba_file_rules."
ok "Connection checks passed"

cat <<EOF

${C_GREEN}${C_BOLD}PostgreSQL $INSTALLED is ready on $PG_LISTEN_ADDR:$PG_PORT (on $LISTEN_IFACE).${C_RESET}

For the application host's environment file (/opt/tabsira/.env). The password
is hex, so it sits in the URL unescaped; it is also in $CREDENTIALS_FILE.

  DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@$PG_LISTEN_ADDR:$PG_PORT/$DB_NAME
  SYNC_DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASSWORD@$PG_LISTEN_ADDR:$PG_PORT/$DB_NAME

Next, on the application host, as devops:
  deploy/deploy.sh --check    the environment file, this database's port and login
  tabsira-deploy              the first deploy migrates the four schemas (app, corpus, geodata, vectors)
  deploy/load-data.sh         scripture, vectors, ontology, learning path (--geonames for the atlas)

Firewall:     not configured here; allow $PG_PORT/tcp from the application host. pg_hba admits $DB_USER from $HBA_SOURCE only.
Tuning:       $TUNING_FILE
Access:       $HBA_FILE (managed block at the end)
Logs:         journalctl -u postgresql@$PG_VERSION-main  ·  /var/log/postgresql/
Slow queries: SELECT calls, mean_exec_time, query FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
EOF
