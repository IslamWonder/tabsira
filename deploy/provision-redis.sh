#!/usr/bin/env bash
# Provision Redis on the production DATA host (Ubuntu 24.04 or 26.04).
# Ported from the reference project's provision/install-redis-production.sh: native
# packages from packages.redis.io, no Docker.
#
# Redis holds what PostgreSQL does poorly (decision 21): scan-progress pub/sub,
# the background job queue, short-lived caches and rate-limit counters. Durable
# state stays in PostgreSQL.
#
#   - bind: 127.0.0.1 and DATA_HOST_VPN_IP (default: the address on wt0). Never
#     every interface. protected-mode yes.
#   - requirepass: generated on the first run, kept in /etc/tabsira/redis.env
#     (root only); a later run re-applies it.
#   - maxmemory 60 % of RAM, volatile-lru: only keys with a TTL (caches,
#     counters) are evicted; queue keys without one are never touched.
#   - AOF on, fsync every second, plus the default RDB snapshots.
#   The host firewall rule for the application host is deploy/provision-data.sh.
#
# Usage (as root, on the data host):
#   deploy/provision-redis.sh [--dry-run]
#
# Environment: DATA_HOST_VPN_IP, VPN_IFACE (wt0), REDIS_MAXMEMORY_MB,
# REDIS_MAXMEMORY_POLICY (volatile-lru), REDIS_DATA_DIR (/var/lib/redis).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"
# shellcheck disable=SC1091
source "$DEPLOY_DIR/net-lib.sh"

[[ "${1:-}" == "--dry-run" ]] && set_dry_run
VPN_IFACE="${VPN_IFACE:-wt0}"
REDIS_MAXMEMORY_MB="${REDIS_MAXMEMORY_MB:-}"
REDIS_MAXMEMORY_POLICY="${REDIS_MAXMEMORY_POLICY:-volatile-lru}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-/var/lib/redis}"
REDIS_PORT=6379
REDIS_CONF=/etc/redis/redis.conf
MANAGED_CONF=/etc/redis/tabsira.conf
CREDENTIALS_FILE="${REDIS_CREDENTIALS_FILE:-/etc/tabsira/redis.env}"

case "$REDIS_MAXMEMORY_POLICY" in
volatile-lru | allkeys-lru | volatile-lfu | allkeys-lfu | volatile-ttl | noeviction) ;;
*) die "REDIS_MAXMEMORY_POLICY '$REDIS_MAXMEMORY_POLICY' is not a supported eviction policy." ;;
esac

if is_dry; then
	banner "DRY RUN: Redis on the data host"
	log "bind          127.0.0.1 and ${DATA_HOST_VPN_IP:-the address on $VPN_IFACE}, port $REDIS_PORT, protected-mode yes"
	log "auth          requirepass, generated into $CREDENTIALS_FILE (root only)"
	log "memory        ${REDIS_MAXMEMORY_MB:-60 % of RAM} MB, $REDIS_MAXMEMORY_POLICY"
	log "persistence   AOF everysec and RDB snapshots in $REDIS_DATA_DIR"
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
MEM_MB=$(($(awk '/^MemTotal:/ { print $2 }' /proc/meminfo) / 1024))
REDIS_MAXMEMORY_MB="${REDIS_MAXMEMORY_MB:-$((MEM_MB * 60 / 100))}"
[[ "$REDIS_MAXMEMORY_MB" =~ ^[0-9]+$ ]] || die "REDIS_MAXMEMORY_MB must be a number of megabytes."
((REDIS_MAXMEMORY_MB < MEM_MB * 85 / 100)) ||
	die "REDIS_MAXMEMORY_MB=$REDIS_MAXMEMORY_MB leaves no room for the AOF rewrite on ${MEM_MB} MB; keep it under 85 % of RAM."

REDIS_PASSWORD=""
[[ -r "$CREDENTIALS_FILE" ]] && REDIS_PASSWORD="$(sed -n 's/^REDIS_PASSWORD=//p' "$CREDENTIALS_FILE" | tail -n 1)"
[[ -n "$REDIS_PASSWORD" ]] || REDIS_PASSWORD="$(openssl rand -hex 24)"
rcli() { redis-cli --no-auth-warning -a "$REDIS_PASSWORD" "$@"; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg openssl >/dev/null
if curl -fsSIo /dev/null "https://packages.redis.io/deb/dists/${CODENAME}/Release"; then
	install -m 0755 -d /etc/apt/keyrings
	[[ -s /etc/apt/keyrings/redis.gpg ]] || curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /etc/apt/keyrings/redis.gpg
	chmod a+r /etc/apt/keyrings/redis.gpg
	echo "deb [signed-by=/etc/apt/keyrings/redis.gpg] https://packages.redis.io/deb ${CODENAME} main" >/etc/apt/sources.list.d/redis.list
	apt-get update -qq
else
	warn "packages.redis.io has no '$CODENAME' suite; installing Ubuntu's redis-server (older)."
fi
apt-get install -y -qq redis-server redis-tools >/dev/null
ok "redis-server $(redis-server --version | sed -n 's/.*v=\([^ ]*\).*/\1/p')"

printf 'vm.overcommit_memory = 1\nnet.core.somaxconn = 1024\nvm.swappiness = 10\n' >/etc/sysctl.d/90-tabsira-redis.conf
sysctl -q --system >/dev/null 2>&1 || warn "Some sysctl keys could not be applied."

install -d -o redis -g redis -m 0750 "$REDIS_DATA_DIR"
log "Writing $MANAGED_CONF"
(
	umask 027
	cat >"$MANAGED_CONF" <<EOF
# Managed by deploy/provision-redis.sh, rewritten on every run.
bind 127.0.0.1 $LISTEN_ADDR
port $REDIS_PORT
protected-mode yes
requirepass $REDIS_PASSWORD
tcp-keepalive 300
maxmemory ${REDIS_MAXMEMORY_MB}mb
maxmemory-policy $REDIS_MAXMEMORY_POLICY
dir $REDIS_DATA_DIR
appendonly yes
appendfsync everysec
aof-use-rdb-preamble yes
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
slowlog-log-slower-than 10000
EOF
)
chown root:redis "$MANAGED_CONF"
chmod 0640 "$MANAGED_CONF"
INCLUDE_LINE="include $MANAGED_CONF"
if [[ "$(tail -n 1 "$REDIS_CONF")" != "$INCLUDE_LINE" ]]; then
	cp -a "$REDIS_CONF" "$REDIS_CONF.bak.$(date +%s)"
	grep -vxF "$INCLUDE_LINE" "$REDIS_CONF" >"$REDIS_CONF.new" || true
	printf '\n%s\n' "$INCLUDE_LINE" >>"$REDIS_CONF.new"
	cat "$REDIS_CONF.new" >"$REDIS_CONF"
	rm -f "$REDIS_CONF.new"
fi

install -d -m 0750 "$(dirname "$CREDENTIALS_FILE")"
(
	umask 077
	printf 'REDIS_HOST=%s\nREDIS_PORT=%s\nREDIS_PASSWORD=%s\n' "$LISTEN_ADDR" "$REDIS_PORT" "$REDIS_PASSWORD" >"$CREDENTIALS_FILE"
)
chmod 0600 "$CREDENTIALS_FILE"

systemctl enable redis-server >/dev/null 2>&1 || true
systemctl restart redis-server
redis_up() { rcli -h 127.0.0.1 -p "$REDIS_PORT" PING 2>/dev/null | grep -q PONG; }
wait_until 30 redis_up || die "Redis did not come back; see journalctl -u redis-server."

rcli -h "$LISTEN_ADDR" -p "$REDIS_PORT" PING | grep -q PONG || die "Nothing answers on $LISTEN_ADDR:$REDIS_PORT."
if redis-cli -h "$LISTEN_ADDR" -p "$REDIS_PORT" PING 2>/dev/null | grep -q PONG; then
	die "Redis answers without a password; requirepass did not apply."
fi
[[ "$(rcli -h 127.0.0.1 CONFIG GET appendonly | tail -n 1)" == yes ]] || die "appendonly is not on; $MANAGED_CONF was not applied."
ok "Redis is ready on $LISTEN_ADDR:$REDIS_PORT (password in $CREDENTIALS_FILE)"
cat <<EOF

For the application host's environment file:

  REDIS_URL=redis://:<REDIS_PASSWORD>@$LISTEN_ADDR:$REDIS_PORT/0
EOF
