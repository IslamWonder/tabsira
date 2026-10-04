#!/usr/bin/env bash
# Provision the production DATA host: PostgreSQL 18 and Redis, reachable only
# over the Netbird VPN (interface wt0) by the application host.
#
#   1. deploy/provision-postgres.sh   packages, extensions, roles, database,
#                                      pg_hba for APP_HOST_VPN_IP/32, nightly dump
#   2. deploy/provision-redis.sh      password, protected mode, no persistence
#   3. the firewall: with ufw, allow 5432 and 6379 in on the VPN interface from
#      APP_HOST_VPN_IP only and deny them from everywhere else. The rules are
#      added; ufw is not enabled and its defaults are not changed, because a
#      wrong default over ssh locks the operator out. If ufw is inactive the
#      script says so; FIREWALL_ENABLE=true enables it after allowing ssh
#      (SSH_PORT, default 22).
#
# Usage (as root, on the data host):
#   APP_HOST_VPN_IP=<netbird address of the app host> deploy/provision-data.sh [--dry-run]
#
# Environment: everything the two scripts read, plus FIREWALL (ufw | none,
# default ufw), FIREWALL_ENABLE (false), SSH_PORT (22).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"
# shellcheck disable=SC1091
source "$DEPLOY_DIR/net-lib.sh"

[[ "${1:-}" == "--dry-run" ]] && set_dry_run
VPN_IFACE="${VPN_IFACE:-wt0}"
FIREWALL="${FIREWALL:-ufw}"
FIREWALL_ENABLE="${FIREWALL_ENABLE:-false}"
SSH_PORT="${SSH_PORT:-22}"
require_app_host

firewall() {
	[[ "$FIREWALL" == "ufw" ]] || {
		warn "FIREWALL=$FIREWALL: no rule written. pg_hba and Redis's password are then the only limits on 5432 and 6379."
		return 0
	}
	have ufw || apt_install ufw
	local port
	for port in 5432 6379; do
		# The allow comes first: ufw evaluates in order.
		run as_root ufw allow in on "$VPN_IFACE" from "$APP_HOST_VPN_IP" to any port "$port" proto tcp comment "tabsira app host"
		run as_root ufw deny in to any port "$port" proto tcp comment "tabsira data ports are VPN only"
	done
	if [[ "$FIREWALL_ENABLE" == "true" ]]; then
		run as_root ufw allow "$SSH_PORT"/tcp comment "ssh"
		run as_root ufw --force enable
	elif ! is_dry && ! as_root ufw status | grep -q "Status: active"; then
		warn "ufw is inactive, so these rules do nothing yet. Allow ssh, then: sudo ufw enable (or FIREWALL_ENABLE=true)."
	fi
}

banner "Data host: PostgreSQL, Redis, firewall (app host $APP_HOST_VPN_IP over $VPN_IFACE)"
if is_dry; then
	bash "$DEPLOY_DIR/provision-postgres.sh" --dry-run
	bash "$DEPLOY_DIR/provision-redis.sh" --dry-run
	firewall
	ok "Dry run complete: nothing was changed."
	exit 0
fi
bash "$DEPLOY_DIR/provision-postgres.sh"
bash "$DEPLOY_DIR/provision-redis.sh"
firewall
ok "Data host provisioned."
