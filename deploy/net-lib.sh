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
	# A missing interface is an empty answer, not a failure (set -o pipefail).
	{ ip -4 -o addr show dev "$1" scope global 2>/dev/null || true; } | awk 'NR == 1 { print $4 }'
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

# This host's own VPN address, for the scripts that run on the application host:
# APP_HOST_VPN_IP when set, else the address on VPN_IFACE (wt0), else the first
# 100.64.0.0/10 address. Nothing to pass by hand when Netbird is up.
detect_app_host() {
	if [[ -z "${APP_HOST_VPN_IP:-}" ]]; then
		local cidr a
		cidr="$(iface_cidr "${VPN_IFACE:-wt0}")"
		APP_HOST_VPN_IP="${cidr%/*}"
		if [[ -z "$APP_HOST_VPN_IP" ]]; then
			for a in $(ip -4 -o addr show scope global 2>/dev/null | awk '{ split($4, p, "/"); print p[1] }'); do
				case "$a" in 100.6[4-9].* | 100.[7-9][0-9].* | 100.1[01][0-9].* | 100.12[0-7].*)
					APP_HOST_VPN_IP="$a"
					break
					;;
				esac
			done
		fi
		[[ -n "$APP_HOST_VPN_IP" ]] ||
			die "No address on ${VPN_IFACE:-wt0} and no 100.64.0.0/10 address on this host. Is Netbird up? Otherwise set APP_HOST_VPN_IP."
	fi
	is_ipv4 "$APP_HOST_VPN_IP" || die "APP_HOST_VPN_IP '$APP_HOST_VPN_IP' must be a single IPv4 address, not a network."
	export APP_HOST_VPN_IP
}

# The application host's VPN address, given by hand on another host: one host, never a network.
require_app_host() {
	[[ -n "${APP_HOST_VPN_IP:-}" ]] || die "Set APP_HOST_VPN_IP to the application host's Netbird address."
	is_ipv4 "$APP_HOST_VPN_IP" || die "APP_HOST_VPN_IP '$APP_HOST_VPN_IP' must be a single IPv4 address, not a network."
}

# Let a service bind an address that is not up yet. Netbird adds its address a
# little after boot, and nginx, PostgreSQL and Redis bind it by name: without
# this one of them can fail to start on a reboot and stay down. Connections to
# that address simply wait until it exists.
NONLOCAL_BIND_SYSCTL=/etc/sysctl.d/90-tabsira-nonlocal-bind.conf
NONLOCAL_BIND_CONTENT='# Written by deploy/. The VPN address may appear after the services that bind it.
net.ipv4.ip_nonlocal_bind = 1'
install_nonlocal_bind() {
	if is_dry; then
		echo "      would write $NONLOCAL_BIND_SYSCTL (net.ipv4.ip_nonlocal_bind = 1) and load it"
		return 0
	fi
	printf '%s\n' "$NONLOCAL_BIND_CONTENT" >"$NONLOCAL_BIND_SYSCTL"
	sysctl -q -p "$NONLOCAL_BIND_SYSCTL" >/dev/null
}
