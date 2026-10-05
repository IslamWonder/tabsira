#!/usr/bin/env bash
# The macOS counterpart of scripts/setup-nginx-local.sh (which dispatches here on
# Darwin): http://tabsira.test, http://api.tabsira.test and
# http://admin.tabsira.test behind Homebrew's nginx, on port 80, without TLS
# (decision 49).
#
# What it changes, and nothing else:
#   - nginx from Homebrew, when it is not installed
#   - $(brew --prefix)/etc/nginx/servers/tabsira.test.conf, from nginx/local/
#     with the log directory rewritten to Homebrew's
#   - /etc/hosts: one line naming the three hosts (when they are not there yet);
#     this is the only step that asks for your password
# Other sites in Homebrew's nginx are never touched, and the configuration must
# pass `nginx -t` before this script writes anything and again after.
#
# Port 80 needs no root on macOS 10.14 and later for a server listening on every
# address, which is how nginx/local/tabsira.test.conf listens, so nginx runs as a
# login service under your account (brew services).
#
# Idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

HOSTS=(tabsira.test api.tabsira.test admin.tabsira.test)
CONF_SRC="$REPO_ROOT/nginx/local/tabsira.test.conf"

is_macos || die "this script is for macOS; on Ubuntu run scripts/setup-nginx-local.sh"
require_cmd brew "Install Homebrew from https://brew.sh"
[[ -f "$CONF_SRC" ]] || die "$CONF_SRC is missing"

if have nginx || brew list --formula nginx >/dev/null 2>&1; then
	ok "Already installed: nginx"
else
	log "Installing nginx"
	brew install nginx
fi

PREFIX="$(brew --prefix)"
NGINX="$PREFIX/bin/nginx"
SERVERS_DIR="$PREFIX/etc/nginx/servers"
SITE="$SERVERS_DIR/tabsira.test.conf"
LOG_DIR="$PREFIX/var/log/nginx"

log "Checking the current nginx configuration"
"$NGINX" -t >/dev/null 2>&1 ||
	die "nginx -t already fails before any change of ours. Fix that first (run: $NGINX -t); nothing was modified."

# ─── The site ───────────────────────────────────────────────────────
mkdir -p "$SERVERS_DIR" "$LOG_DIR"
previous=""
[[ -f "$SITE" ]] && previous="$(cat "$SITE")"
sed "s#/var/log/nginx/#$LOG_DIR/#g" "$CONF_SRC" >"$SITE"
if ! "$NGINX" -t >/dev/null 2>&1; then
	if [[ -n "$previous" ]]; then printf '%s\n' "$previous" >"$SITE"; else rm -f "$SITE"; fi
	"$NGINX" -t || true
	die "nginx -t fails with the TABSIRA site; the previous state was put back"
fi
ok "Wrote $SITE"

# ─── /etc/hosts ─────────────────────────────────────────────────────
missing=()
for host in "${HOSTS[@]}"; do
	grep -qE "^[^#]*[[:space:]]${host}([[:space:]]|\$)" /etc/hosts || missing+=("$host")
done
if [[ ${#missing[@]} -gt 0 ]]; then
	line="127.0.0.1 ${missing[*]}"
	log "Adding to /etc/hosts: $line (asks for your password)"
	printf '%s\n' "$line" | sudo tee -a /etc/hosts >/dev/null ||
		die "could not edit /etc/hosts. Run: echo '$line' | sudo tee -a /etc/hosts   then run this script again"
else
	ok "/etc/hosts already names ${HOSTS[*]}"
fi

# ─── Run ────────────────────────────────────────────────────────────
brew services start nginx >/dev/null
brew services reload nginx >/dev/null 2>&1 || brew services restart nginx >/dev/null

waited=0
until [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://tabsira.test/ 2>/dev/null)" =~ ^(200|3..|502)$ ]]; do
	((waited < 15)) || die "http://tabsira.test does not answer on port 80 (log: $LOG_DIR/error.log)"
	sleep 1
	waited=$((waited + 1))
done

ok "http://tabsira.test, http://api.tabsira.test and http://admin.tabsira.test are served by nginx"
cat <<EOF

  Web   http://tabsira.test       -> 127.0.0.1:3000
  API   http://api.tabsira.test   -> 127.0.0.1:8000
  Admin http://admin.tabsira.test -> 127.0.0.1:8000 (/admin)

  A 502 Bad Gateway is expected until the apps run: make dev
EOF
