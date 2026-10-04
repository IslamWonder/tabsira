#!/usr/bin/env bash
#
# provision-redis.sh — standalone Redis installer for the production cache host
# (redis.tabsira.me) on Ubuntu 24.04 LTS (26.04 works too). Native packages from
# packages.redis.io, no Docker. One file: copy it to the host and run it as root;
# it needs nothing else from the repository.
#
# Redis holds what PostgreSQL does poorly (decision 21): scan-progress pub/sub, the
# background job queue, short-lived caches and rate-limit counters. Durable state
# stays in PostgreSQL.
#
# What it does, in order:
#   1. Adds the redis.io apt repository and installs the latest Redis 8
#      (redis-server + redis-tools). If redis.io has no suite for this Ubuntu
#      release yet, it falls back to Ubuntu's package and says so.
#   2. Sets the system timezone to UTC and tunes the kernel the way Redis asks for
#      at start-up: overcommit_memory, somaxconn, transparent huge pages off,
#      swappiness; and net.ipv4.ip_nonlocal_bind, so a reboot that starts Redis
#      before Netbird has given its address does not leave Redis down.
#   3. Writes one managed file, /etc/redis/tabsira.conf, included at the end of
#      redis.conf so its directives win. Rewritten on every run; change the
#      variables below or override them in the environment instead of editing it:
#        - bind: loopback and this host's Netbird VPN address (the one on
#          REDIS_VPN_IFACE, wt0). Never every interface. protected-mode yes.
#        - requirepass: generated on the first run and kept in
#          /etc/tabsira/redis.env (root only); later runs re-apply it.
#        - maxmemory REDIS_MAXMEMORY_MB (default 60 % of RAM), volatile-lru: only
#          keys with a TTL (caches, counters) are evicted; the job queue is never touched.
#        - Persistence OFF for the whole instance (no AOF, no RDB). The scan
#          workflow keeps users' photos here (sealed with AES-GCM, expiring after
#          an hour) beside its job queue, and Redis cannot persist one database
#          and not another: nothing of them ever reaches a disk. The price: a
#          Redis restart empties the queue, the progress events and the rate-limit
#          counters; a scan caught by it fails and the person scans again. Any
#          dump.rdb or append-only file an earlier run left is deleted.
#   4. Verifies: PING with the password on loopback and the VPN address, that a
#      connection without the password is refused, and that persistence is off.
#
# It ends by printing the REDIS_URL and REDIS_PASSWORD lines for the application
# host's environment file. The URL carries no password: the API refuses one.
#
# It does not touch the host firewall: allow 6379/tcp from the application host
# (or REDIS_APP_SUBNET, the VPN network, printed below) in the firewall you use.
# Until then the bind list and the password are what limit access to 6379.
#
# Re-running is safe and is how you apply a change or pick up a new release.
#
# Settings (environment variables, all optional):
#   REDIS_VPN_IFACE        Netbird interface                       (default: wt0)
#   REDIS_LISTEN_ADDR      This host's VPN address (default: the IPv4 on REDIS_VPN_IFACE,
#                          else the first 100.64.0.0/10 address)
#   REDIS_APP_SUBNET       CIDR the application host reaches us from, reported for the
#                          firewall (default: the network of REDIS_LISTEN_ADDR)
#   REDIS_PASSWORD         (default: read from /etc/tabsira/redis.env, generated on the first run)
#   REDIS_MAXMEMORY_MB     (default: 60 % of RAM)
#   REDIS_MAXMEMORY_POLICY (default: volatile-lru)
#   REDIS_DATA_DIR         (default: /var/lib/redis)
#
# Usage:
#   sudo ./provision-redis.sh [--check]
#
# Options:
#   --check     Detect, validate and print the plan; change nothing (--dry-run works too)
#   -h, --help
#
set -Eeuo pipefail

# ---------- defaults ----------
REDIS_VPN_IFACE="${REDIS_VPN_IFACE:-${VPN_IFACE:-wt0}}"
REDIS_LISTEN_ADDR="${REDIS_LISTEN_ADDR:-${DATA_HOST_VPN_IP:-}}"
REDIS_APP_SUBNET="${REDIS_APP_SUBNET:-}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_MAXMEMORY_MB="${REDIS_MAXMEMORY_MB:-}"
REDIS_MAXMEMORY_POLICY="${REDIS_MAXMEMORY_POLICY:-volatile-lru}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-/var/lib/redis}"
REDIS_PORT=6379

REDIS_CONF=/etc/redis/redis.conf
MANAGED_CONF=/etc/redis/tabsira.conf
CREDENTIALS_FILE=/etc/tabsira/redis.env
CHECK_ONLY=0

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

is_cidr() { [[ $1 =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]; }

# The first global IPv4 (with prefix, a.b.c.d/nn) on interface $1.
iface_addr() {
	ip -4 -o addr show dev "$1" scope global 2>/dev/null | awk 'NR == 1 { print $4 }'
}

# The prefix length the host's interface declares for address $1, or nothing.
prefix_of() {
	ip -4 -o addr show scope global 2>/dev/null | awk -v a="$1" '{ split($4, p, "/"); if (p[1] == a) { print p[2]; exit } }'
}

# The network of a.b.c.d/nn as a CIDR, e.g. 100.73.74.74/16 -> 100.73.0.0/16.
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

rcli() { redis-cli --no-auth-warning -a "$REDIS_PASSWORD" "$@"; }

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
[[ -r /etc/os-release ]] || die "Cannot read /etc/os-release."
# shellcheck disable=SC1091
. /etc/os-release
[[ ${ID:-} == ubuntu ]] || die "This installer targets Ubuntu (got: ${ID:-unknown})."
CODENAME="${VERSION_CODENAME:?no VERSION_CODENAME in /etc/os-release}"
case "${VERSION_ID:-}" in
24.04 | 26.04) ;;
*) warn "Written for Ubuntu 24.04 / 26.04; this is ${VERSION_ID:-unknown}." ;;
esac
log "Ubuntu ${VERSION_ID:-?} ($CODENAME)"

case "$REDIS_MAXMEMORY_POLICY" in
volatile-lru | allkeys-lru | volatile-lfu | allkeys-lfu | volatile-random | allkeys-random | volatile-ttl | noeviction) ;;
*) die "REDIS_MAXMEMORY_POLICY '$REDIS_MAXMEMORY_POLICY' is not a Redis eviction policy." ;;
esac

# ---------- addresses ----------
if [[ -z $REDIS_LISTEN_ADDR ]]; then
	VPN_CIDR="$(iface_addr "$REDIS_VPN_IFACE")"
	if [[ -n $VPN_CIDR ]]; then
		REDIS_LISTEN_ADDR="${VPN_CIDR%/*}"
	else
		REDIS_LISTEN_ADDR="$(detect_vpn_addr)" ||
			die "No address on $REDIS_VPN_IFACE and no 100.64.0.0/10 address on this host. Is Netbird up? Otherwise set REDIS_LISTEN_ADDR."
		warn "$REDIS_VPN_IFACE has no address; using $REDIS_LISTEN_ADDR from the CGNAT range instead."
	fi
fi
case "$REDIS_LISTEN_ADDR" in
'*' | 0.0.0.0 | '::' | '') die "Refusing to bind a production Redis to every interface." ;;
esac
LISTEN_PREFIX="$(prefix_of "$REDIS_LISTEN_ADDR")"
[[ -n $LISTEN_PREFIX ]] || die "REDIS_LISTEN_ADDR=$REDIS_LISTEN_ADDR is not an address of this host."
LISTEN_IFACE="$(ip -4 -o addr show scope global | awk -v a="$REDIS_LISTEN_ADDR" '{ split($4, p, "/"); if (p[1] == a) { print $2; exit } }')"
if [[ -z $REDIS_APP_SUBNET ]]; then
	REDIS_APP_SUBNET="$(network_of "$REDIS_LISTEN_ADDR/$LISTEN_PREFIX")"
fi
is_cidr "$REDIS_APP_SUBNET" || die "REDIS_APP_SUBNET must be an IPv4 CIDR such as 100.73.0.0/16 (got '$REDIS_APP_SUBNET')."
[[ ${REDIS_APP_SUBNET##*/} -ge 8 ]] || die "Refusing REDIS_APP_SUBNET=$REDIS_APP_SUBNET; name the network the application host reaches us from."
BIND="127.0.0.1 $REDIS_LISTEN_ADDR"

# ---------- credentials ----------
PASSWORD_SOURCE="from the environment"
if [[ -z $REDIS_PASSWORD && -r $CREDENTIALS_FILE ]]; then
	REDIS_PASSWORD="$(sed -n 's/^REDIS_PASSWORD=//p' "$CREDENTIALS_FILE" | tail -n1)"
	PASSWORD_SOURCE="from $CREDENTIALS_FILE"
fi
if [[ -z $REDIS_PASSWORD ]]; then
	command -v openssl >/dev/null || die "openssl is required to generate a password."
	REDIS_PASSWORD="$(openssl rand -hex 24)"
	PASSWORD_SOURCE="generated now"
fi
[[ $REDIS_PASSWORD =~ ^[A-Za-z0-9._~-]+$ ]] ||
	die "REDIS_PASSWORD may only contain letters, digits and . _ ~ - so it can sit in a URL unescaped."

# ---------- memory ----------
MEM_MB=$(($(awk '/^MemTotal:/ { print $2 }' /proc/meminfo) / 1024))
if [[ -z $REDIS_MAXMEMORY_MB ]]; then
	REDIS_MAXMEMORY_MB=$((MEM_MB * 60 / 100))
fi
[[ $REDIS_MAXMEMORY_MB =~ ^[0-9]+$ ]] || die "REDIS_MAXMEMORY_MB must be a number of megabytes."
[[ $REDIS_MAXMEMORY_MB -lt $((MEM_MB * 85 / 100)) ]] ||
	die "REDIS_MAXMEMORY_MB=$REDIS_MAXMEMORY_MB leaves too little room on a ${MEM_MB} MB host; keep it under 85 % of RAM."

cat <<EOF

  Redis          latest 8.x from packages.redis.io ($CODENAME)
  Bind           $BIND (port $REDIS_PORT, protected-mode yes, password $PASSWORD_SOURCE)
  Address        $REDIS_LISTEN_ADDR/$LISTEN_PREFIX on $LISTEN_IFACE$([[ $LISTEN_IFACE == "$REDIS_VPN_IFACE" ]] && echo " (Netbird VPN)")
  Credentials    $CREDENTIALS_FILE (root only)
  Firewall       not managed here; allow $REDIS_PORT/tcp from the application host ($REDIS_APP_SUBNET)
  Host           ${MEM_MB} MB RAM
  Memory         maxmemory ${REDIS_MAXMEMORY_MB}mb, $REDIS_MAXMEMORY_POLICY
  Persistence    OFF (no AOF, no RDB): photos sealed in Redis never reach a disk

EOF

if ((CHECK_ONLY)); then
	ok "--check: nothing changed."
	exit 0
fi

# ---------- packages ----------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg openssl >/dev/null
rm -f /etc/apt/sources.list.d/redislabs-redis-*.list
if curl -fsSIo /dev/null "https://packages.redis.io/deb/dists/${CODENAME}/Release"; then
	KEYRING=/etc/apt/keyrings/redis.gpg
	if [[ ! -s $KEYRING ]]; then
		log "Adding the redis.io signing key"
		install -m 0755 -d /etc/apt/keyrings
		curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o "$KEYRING"
		chmod a+r "$KEYRING"
	fi
	REDIS_LIST=/etc/apt/sources.list.d/redis.list
	REDIS_LINE="deb [signed-by=$KEYRING] https://packages.redis.io/deb ${CODENAME} main"
	if [[ ! -f $REDIS_LIST ]] || ! grep -qxF "$REDIS_LINE" "$REDIS_LIST"; then
		log "Adding the redis.io apt repository for $CODENAME"
		echo "$REDIS_LINE" >"$REDIS_LIST"
	fi
	apt-get update -qq
	SOURCE="packages.redis.io"
else
	warn "packages.redis.io has no '$CODENAME' suite; installing Ubuntu's redis-server instead (older)."
	SOURCE="Ubuntu"
fi
log "Installing Redis from $SOURCE"
apt-get install -y -qq redis-server redis-tools >/dev/null
INSTALLED="$(redis-server --version | sed -n 's/.*v=\([^ ]*\).*/\1/p')"
ok "redis-server $INSTALLED ($(dpkg-query -W -f='${Version}' redis-server))"
[[ ${INSTALLED%%.*} -ge 8 ]] || warn "Redis $INSTALLED is older than 8."

# ---------- time ----------
if [[ "$(timedatectl show -p Timezone --value 2>/dev/null || true)" != UTC ]]; then
	log "Setting the system timezone to UTC"
	timedatectl set-timezone UTC 2>/dev/null || {
		ln -sf /usr/share/zoneinfo/UTC /etc/localtime
		echo UTC >/etc/timezone
	}
fi

# ---------- kernel ----------
log "Kernel settings for a Redis host"
cat >/etc/sysctl.d/90-tabsira-redis.conf <<'EOF'
# Written by deploy/provision-redis.sh
vm.overcommit_memory = 1
# Redis raises its backlog to 511 and asks for at least that much.
net.core.somaxconn = 1024
vm.swappiness = 10
# Netbird adds its address a little after boot; Redis binds it by name.
net.ipv4.ip_nonlocal_bind = 1
EOF
sysctl -q --system >/dev/null 2>&1 || warn "Some sysctl keys could not be applied (fine inside a container, not on a VM)."

# Transparent huge pages slow Redis down; the setting does not survive a reboot on its own.
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
systemctl daemon-reload
systemctl enable --now tabsira-disable-thp.service >/dev/null 2>&1 || warn "Could not disable transparent huge pages (not a fatal problem)."

# Start Redis after Netbird when the VPN client is installed (ordering only).
install -d /etc/systemd/system/redis-server.service.d
cat >/etc/systemd/system/redis-server.service.d/tabsira-netbird.conf <<'EOF'
# Written by deploy/provision-redis.sh
[Unit]
After=netbird.service
EOF

# ---------- configuration (managed include) ----------
[[ -f $REDIS_CONF ]] || die "$REDIS_CONF is missing; the package did not install its configuration."
install -d -o redis -g redis -m 0750 "$REDIS_DATA_DIR"
DROPIN_DIR=/etc/systemd/system/redis-server.service.d
if [[ $REDIS_DATA_DIR != /var/lib/redis ]]; then
	cat >"$DROPIN_DIR/tabsira-datadir.conf" <<EOF
# Written by deploy/provision-redis.sh
[Service]
ReadWriteDirectories=-$REDIS_DATA_DIR
EOF
else
	rm -f "$DROPIN_DIR/tabsira-datadir.conf"
fi
systemctl daemon-reload

log "Writing $MANAGED_CONF"
umask 027
cat >"$MANAGED_CONF" <<EOF
# Managed by deploy/provision-redis.sh — rewritten on every run.
# Included from the last line of redis.conf, so these directives win.

# --- network ---
bind $BIND
port $REDIS_PORT
protected-mode yes
requirepass $REDIS_PASSWORD
tcp-keepalive 300
timeout 0

# --- memory ---
maxmemory ${REDIS_MAXMEMORY_MB}mb
maxmemory-policy $REDIS_MAXMEMORY_POLICY

# --- persistence: off, on purpose (scanned photos wait here, sealed) ---
dir $REDIS_DATA_DIR
appendonly no
save ""

# --- observability ---
loglevel notice
slowlog-log-slower-than 10000
slowlog-max-len 256
latency-monitor-threshold 100
EOF
umask 022
chown root:redis "$MANAGED_CONF"
chmod 0640 "$MANAGED_CONF"

INCLUDE_LINE="include $MANAGED_CONF"
if ! [[ "$(tail -n1 "$REDIS_CONF")" == "$INCLUDE_LINE" ]]; then
	log "Appending '$INCLUDE_LINE' to $REDIS_CONF"
	cp -a "$REDIS_CONF" "$REDIS_CONF.bak.$(date +%s)"
	sed -i "\|^$INCLUDE_LINE\$|d" "$REDIS_CONF"
	printf '\n%s\n' "$INCLUDE_LINE" >>"$REDIS_CONF"
fi

# ---------- credentials file ----------
install -d -m 0750 /etc/tabsira
umask 077
cat >"$CREDENTIALS_FILE" <<EOF
# Written by deploy/provision-redis.sh. Root only.
# Re-running the installer re-applies REDIS_PASSWORD, so change it here and
# re-run rather than with CONFIG SET.
REDIS_HOST=$REDIS_LISTEN_ADDR
REDIS_PORT=$REDIS_PORT
REDIS_PASSWORD=$REDIS_PASSWORD
EOF
umask 022
chmod 0600 "$CREDENTIALS_FILE"

# ---------- restart and wait ----------
log "Restarting redis-server (stopped first, so no shutdown snapshot is written)"
systemctl enable redis-server >/dev/null 2>&1 || true
systemctl stop redis-server || true
rm -rf "${REDIS_DATA_DIR:?}/dump.rdb" "${REDIS_DATA_DIR:?}/appendonlydir" "${REDIS_DATA_DIR:?}"/temp-*.rdb
systemctl start redis-server
for _ in $(seq 1 20); do
	rcli -h 127.0.0.1 -p "$REDIS_PORT" PING 2>/dev/null | grep -q PONG && break
	sleep 1
done
rcli -h 127.0.0.1 -p "$REDIS_PORT" PING 2>/dev/null | grep -q PONG || {
	journalctl -u redis-server -n 30 --no-pager >&2 || true
	die "Redis did not come back after the restart; see the log above and $MANAGED_CONF."
}
ok "Redis is up: $(rcli -h 127.0.0.1 INFO server | sed -n 's/^redis_version://p' | tr -d '\r')"

# ---------- verify ----------
log "Verifying the VPN listener, the password and that nothing is persisted"
rcli -h "$REDIS_LISTEN_ADDR" -p "$REDIS_PORT" PING | grep -q PONG || die "Nothing answers on $REDIS_LISTEN_ADDR:$REDIS_PORT."
if redis-cli -h "$REDIS_LISTEN_ADDR" -p "$REDIS_PORT" PING 2>/dev/null | grep -q PONG; then
	die "Redis on $REDIS_LISTEN_ADDR answers without a password; requirepass did not apply."
fi
[[ "$(rcli -h 127.0.0.1 CONFIG GET appendonly | tail -n1)" == no ]] || die "appendonly is not off; $MANAGED_CONF was not applied."
[[ -z "$(rcli -h 127.0.0.1 CONFIG GET save | tail -n1)" ]] || die "RDB snapshots are not off; $MANAGED_CONF was not applied."
[[ "$(rcli -h 127.0.0.1 CONFIG GET maxmemory-policy | tail -n1)" == "$REDIS_MAXMEMORY_POLICY" ]] || die "maxmemory-policy was not applied."
ok "Connection and configuration checks passed"

cat <<EOF

${C_GREEN}${C_BOLD}Redis $INSTALLED is ready on $REDIS_LISTEN_ADDR:$REDIS_PORT (on $LISTEN_IFACE).${C_RESET}

For the application host's environment file (/opt/tabsira/shared/.env). The URL
carries no password: the API refuses one. The password is also in $CREDENTIALS_FILE.

  REDIS_URL=redis://$REDIS_LISTEN_ADDR:$REDIS_PORT/0
  REDIS_PASSWORD=$REDIS_PASSWORD

Firewall: not configured here; allow $REDIS_PORT/tcp from the application host ($REDIS_APP_SUBNET)
Config:   $MANAGED_CONF (included from $REDIS_CONF)
Logs:     journalctl -u redis-server
Health:   redis-cli -a "\$(sudo sed -n s/^REDIS_PASSWORD=//p $CREDENTIALS_FILE)" INFO memory
EOF
