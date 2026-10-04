#!/usr/bin/env bash
# Put https://tabsira.test and https://api.tabsira.test behind the machine's
# nginx, with a certificate from mkcert (a local certificate authority that your
# browser and curl trust once `mkcert -install` has run).
#
#   https://tabsira.test      -> web  127.0.0.1:3000
#   https://api.tabsira.test  -> API  127.0.0.1:8000
#
# What it changes, and nothing else:
#   - /etc/nginx/sites-available/tabsira.test.conf and its sites-enabled link
#   - /etc/nginx/certs/tabsira.test.pem and tabsira.test-key.pem
#   - /etc/hosts: one line naming the two hosts (when they are not there yet)
#   - the mkcert certificate authority in ~/.local/share/mkcert, trusted by the
#     system store and your browsers (`mkcert -install`, one time)
# Other nginx sites are never touched: no default site is removed, and the
# configuration must already pass `nginx -t` before this script writes anything.
# If the test fails afterwards, every file above is put back as it was.
#
# Idempotent. Debian and Ubuntu layout (sites-available / sites-enabled).
# Needs sudo. The mkcert key and certificate stay in nginx/local/certs (gitignored).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

MKCERT_VERSION="${MKCERT_VERSION:-1.4.4}"
HOSTS=(tabsira.test api.tabsira.test)
SITE="tabsira.test"
CONF_SRC="$REPO_ROOT/nginx/local/$SITE.conf"
CERT_DIR_LOCAL="$REPO_ROOT/nginx/local/certs"
SITES_AVAILABLE="/etc/nginx/sites-available/$SITE.conf"
SITES_ENABLED="/etc/nginx/sites-enabled/$SITE.conf"
NGINX_CERT_DIR="/etc/nginx/certs"
NGINX_CERT="$NGINX_CERT_DIR/$SITE.pem"
NGINX_KEY="$NGINX_CERT_DIR/$SITE-key.pem"

is_linux || die "this script configures a Debian or Ubuntu nginx; on another system add the two hosts to your own proxy"
require_sudo
[[ -f "$CONF_SRC" ]] || die "$CONF_SRC is missing"

# ─── Packages ───────────────────────────────────────────────────────
apt_install nginx libnss3-tools

if ! have mkcert; then
	if apt-cache show mkcert >/dev/null 2>&1; then
		apt_install mkcert
	else
		log "mkcert is not in apt; downloading v$MKCERT_VERSION"
		case "$(uname -m)" in
		x86_64 | amd64) arch="amd64" ;;
		aarch64 | arm64) arch="arm64" ;;
		*) die "unsupported CPU: $(uname -m)" ;;
		esac
		tmp="$(mktemp)"
		curl -fsSL -o "$tmp" "https://github.com/FiloSottile/mkcert/releases/download/v${MKCERT_VERSION}/mkcert-v${MKCERT_VERSION}-linux-${arch}"
		as_root install -m 0755 "$tmp" /usr/local/bin/mkcert
		rm -f "$tmp"
	fi
fi
have mkcert || die "mkcert could not be installed"

# ─── The nginx we are about to change must be healthy already ───────
log "Checking the current nginx configuration"
as_root nginx -t >/dev/null 2>&1 ||
	die "nginx -t already fails before any change of ours. Fix that first (run: sudo nginx -t); nothing was modified."

# ─── Back up what we may change, restore it if anything fails ───────
BACKUP="$(mktemp -d)"
ROLLBACK=false
HOSTS_ADDED=""
had_conf=false had_link=false had_cert=false had_key=false
[[ -f "$SITES_AVAILABLE" ]] && had_conf=true && as_root cp -p "$SITES_AVAILABLE" "$BACKUP/conf"
[[ -L "$SITES_ENABLED" ]] && had_link=true
[[ -f "$NGINX_CERT" ]] && had_cert=true && as_root cp -p "$NGINX_CERT" "$BACKUP/cert"
[[ -f "$NGINX_KEY" ]] && had_key=true && as_root cp -p "$NGINX_KEY" "$BACKUP/key"

restore() {
	err "Restoring the previous nginx and hosts state"
	if $had_conf; then as_root cp -p "$BACKUP/conf" "$SITES_AVAILABLE"; else as_root rm -f "$SITES_AVAILABLE"; fi
	if ! $had_link; then as_root rm -f "$SITES_ENABLED"; fi
	if $had_cert; then as_root cp -p "$BACKUP/cert" "$NGINX_CERT"; else as_root rm -f "$NGINX_CERT"; fi
	if $had_key; then as_root cp -p "$BACKUP/key" "$NGINX_KEY"; else as_root rm -f "$NGINX_KEY"; fi
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

# ─── mkcert authority and certificate ───────────────────────────────
log "Installing and trusting the local mkcert authority (system store and browsers)"
mkcert -install

CAROOT="$(mkcert -CAROOT)"
if [[ -f "$CAROOT/rootCA.pem" ]]; then
	# For importing into a browser that does not use the system store (Firefox on
	# some setups). Gitignored; never the key.
	install -m 0644 "$CAROOT/rootCA.pem" "$REPO_ROOT/rootCA.pem"
fi

mkdir -p "$CERT_DIR_LOCAL"
LOCAL_CERT="$CERT_DIR_LOCAL/$SITE.pem"
LOCAL_KEY="$CERT_DIR_LOCAL/$SITE-key.pem"
cert_covers_hosts() {
	local text host
	[[ -f "$LOCAL_CERT" && -f "$LOCAL_KEY" ]] || return 1
	openssl x509 -in "$LOCAL_CERT" -noout -checkend 2592000 >/dev/null 2>&1 || return 1
	text="$(openssl x509 -in "$LOCAL_CERT" -noout -ext subjectAltName 2>/dev/null)" || return 1
	for host in "${HOSTS[@]}"; do
		[[ "$text" == *"DNS:$host"* ]] || return 1
	done
}
if cert_covers_hosts; then
	ok "Certificate for ${HOSTS[*]} already exists and is valid"
else
	log "Creating a certificate for ${HOSTS[*]}"
	mkcert -cert-file "$LOCAL_CERT" -key-file "$LOCAL_KEY" "${HOSTS[@]}"
fi

# ─── Install into nginx, from here on every failure rolls back ──────
ROLLBACK=true
as_root mkdir -p "$NGINX_CERT_DIR"
as_root install -m 0644 "$LOCAL_CERT" "$NGINX_CERT"
as_root install -m 0600 "$LOCAL_KEY" "$NGINX_KEY"
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

ok "https://tabsira.test and https://api.tabsira.test are served by nginx"
cat <<EOF

  Web   https://tabsira.test      -> 127.0.0.1:3000
  API   https://api.tabsira.test  -> 127.0.0.1:8000

  A 502 Bad Gateway is expected until the apps run: make dev
  Chrome, Edge and curl trust the certificate through the system store.
  Firefox: Settings > Privacy & Security > Certificates > View Certificates >
  Authorities > Import > $REPO_ROOT/rootCA.pem
EOF
