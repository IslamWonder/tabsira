#!/usr/bin/env bash
# Put http://tabsira.test, http://api.tabsira.test and http://admin.tabsira.test
# behind the machine's nginx, on port 80 and without TLS (decision 49).
#
#   http://tabsira.test       -> web  127.0.0.1:3000
#   http://api.tabsira.test   -> API  127.0.0.1:8000
#   http://admin.tabsira.test -> API  127.0.0.1:8000, /admin only
#
# What it changes, and nothing else:
#   - /etc/nginx/sites-available/tabsira.test.conf and its sites-enabled link
#   - /etc/hosts: one line naming the three hosts (when they are not there yet)
# A certificate and key an earlier HTTPS setup left in /etc/nginx/certs are
# not touched; nothing reads them any more.
# Other nginx sites are never touched: no default site is removed, and the
# configuration must already pass `nginx -t` before this script writes anything.
# If the test fails afterwards, every file above is put back as it was.
#
# Idempotent. Debian and Ubuntu layout (sites-available / sites-enabled).
# Needs sudo.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

HOSTS=(tabsira.test api.tabsira.test admin.tabsira.test)
SITE="tabsira.test"
CONF_SRC="$REPO_ROOT/nginx/local/$SITE.conf"
SITES_AVAILABLE="/etc/nginx/sites-available/$SITE.conf"
SITES_ENABLED="/etc/nginx/sites-enabled/$SITE.conf"

is_linux || die "this script configures a Debian or Ubuntu nginx; on another system add the three hosts to your own proxy"
require_sudo
[[ -f "$CONF_SRC" ]] || die "$CONF_SRC is missing"

# ─── Packages ───────────────────────────────────────────────────────
apt_install nginx

# ─── The nginx we are about to change must be healthy already ───────
log "Checking the current nginx configuration"
as_root nginx -t >/dev/null 2>&1 ||
	die "nginx -t already fails before any change of ours. Fix that first (run: sudo nginx -t); nothing was modified."

# ─── Back up what we may change, restore it if anything fails ───────
BACKUP="$(mktemp -d)"
ROLLBACK=false
HOSTS_ADDED=""
had_conf=false had_link=false
[[ -f "$SITES_AVAILABLE" ]] && had_conf=true && as_root cp -p "$SITES_AVAILABLE" "$BACKUP/conf"
[[ -L "$SITES_ENABLED" ]] && had_link=true

restore() {
	err "Restoring the previous nginx and hosts state"
	if $had_conf; then as_root cp -p "$BACKUP/conf" "$SITES_AVAILABLE"; else as_root rm -f "$SITES_AVAILABLE"; fi
	if ! $had_link; then as_root rm -f "$SITES_ENABLED"; fi
	if [[ -n "$HOSTS_ADDED" ]]; then
		# Remove exactly the line we appended, leave anything else in /etc/hosts alone.
		grep -vxF "$HOSTS_ADDED" /etc/hosts | as_root tee /etc/hosts.tabsira-restore >/dev/null &&
			as_root cp /etc/hosts.tabsira-restore /etc/hosts && as_root rm -f /etc/hosts.tabsira-restore
	fi
	if as_root nginx -t >/dev/null 2>&1; then
		as_root systemctl reload nginx 2>/dev/null || as_root nginx -s reload || true
	fi
}
cleanup() {
	local rc=$?
	if [[ $rc -ne 0 ]] && $ROLLBACK; then restore; fi
	rm -rf "$BACKUP"
	exit $rc
}
trap cleanup EXIT

# ─── Install into nginx, from here on every failure rolls back ──────
ROLLBACK=true
as_root install -m 0644 "$CONF_SRC" "$SITES_AVAILABLE"
if [[ ! -L "$SITES_ENABLED" ]]; then
	as_root ln -s "$SITES_AVAILABLE" "$SITES_ENABLED"
fi

missing=()
for host in "${HOSTS[@]}"; do
	grep -qE "^[^#]*[[:space:]]${host}([[:space:]]|\$)" /etc/hosts || missing+=("$host")
done
if [[ ${#missing[@]} -gt 0 ]]; then
	HOSTS_ADDED="127.0.0.1 ${missing[*]}"
	log "Adding to /etc/hosts: $HOSTS_ADDED"
	printf '%s\n' "$HOSTS_ADDED" | as_root tee -a /etc/hosts >/dev/null
fi

log "Validating the nginx configuration"
as_root nginx -t
log "Reloading nginx"
as_root systemctl reload nginx 2>/dev/null || as_root nginx -s reload
ROLLBACK=false

ok "http://tabsira.test, http://api.tabsira.test and http://admin.tabsira.test are served by nginx"
cat <<EOF

  Web   http://tabsira.test       -> 127.0.0.1:3000
  API   http://api.tabsira.test   -> 127.0.0.1:8000
  Admin http://admin.tabsira.test -> 127.0.0.1:8000 (/admin)

  A 502 Bad Gateway is expected until the apps run: make dev
  Plain HTTP on port 80: no certificate to trust. A browser that remembers an
  earlier HTTPS setup of these names may need its HSTS entry for them cleared.
EOF
