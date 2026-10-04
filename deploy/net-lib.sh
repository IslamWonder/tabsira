#!/usr/bin/env bash
# Address helpers of the data-host provisioning scripts (Linux, iproute2).
# Source it after set -Eeuo pipefail and deploy/lib.sh.

# A single IPv4 address.
is_ipv4() {
	[[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
	local part
	for part in ${1//./ }; do
		((part <= 255)) || return 1
	done
}

# The first global IPv4 (a.b.c.d/nn) on interface $1; nothing when there is none.
iface_cidr() {
	ip -4 -o addr show dev "$1" scope global 2>/dev/null | awk 'NR == 1 { print $4 }'
}

# Is IPv4 address $1 one of this host's addresses?
is_local_addr() {
	ip -4 -o addr show scope global 2>/dev/null | awk '{ split($4, p, "/"); print p[1] }' | grep -qx "$1"
}

# Resolve the address a data service listens on besides loopback: the one
# given, else the one on the VPN interface. Never every interface.
resolve_listen_addr() {
	local given="$1" iface="$2" cidr
	if [[ -z "$given" ]]; then
		cidr="$(iface_cidr "$iface")"
		[[ -n "$cidr" ]] || die "No address on $iface. Is Netbird up? Otherwise set DATA_HOST_VPN_IP."
		given="${cidr%/*}"
	fi
	case "$given" in
	'' | '*' | 0.0.0.0 | '::') die "Refusing to bind a production data service to every interface." ;;
	esac
	is_ipv4 "$given" || die "DATA_HOST_VPN_IP '$given' is not an IPv4 address."
	is_local_addr "$given" || die "DATA_HOST_VPN_IP $given is not an address of this host."
	printf '%s' "$given"
}

# The application host's VPN address: required, one host, never a network.
require_app_host() {
	[[ -n "${APP_HOST_VPN_IP:-}" ]] || die "Set APP_HOST_VPN_IP to the application host's Netbird address."
	is_ipv4 "$APP_HOST_VPN_IP" || die "APP_HOST_VPN_IP '$APP_HOST_VPN_IP' must be a single IPv4 address, not a network."
}
