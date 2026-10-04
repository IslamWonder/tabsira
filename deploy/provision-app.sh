#!/usr/bin/env bash
# Provision the production APPLICATION host (Ubuntu 24.04 or 26.04): the user,
# Node and pnpm and pm2, uv and Python 3.12, nginx with HTTPS from certbot, the
# systemd units, log rotation and the layout deploy/deploy.sh expects.
# No Docker.
#
# What it does, in order:
#   1. apt packages: nginx, certbot (and its DNS plugin), git, curl,
#      postgresql-client-18 from PGDG (psql and pg_dump for migrations and dumps).
#   2. The application user (no login password) and the layout under APP_ROOT:
#      repo, releases, shared (.env, state, cache), static; /var/log/tabsira.
#   3. Node (the latest 24.x from nodejs.org, checksum verified) with corepack
#      for pnpm and pm2 globally; pm2 starts at boot for the application user.
#   4. uv for the application user, and the Python that apps/api/.python-version
#      names, as uv builds it (never the system Python).
#   5. The production environment file from deploy/env.production.example, only
#      when none exists (mode 0600); HASH_SECRET is generated when still a
#      placeholder. Every other CHANGE_ME stays for the owners.
#   6. TLS: certbot issues the certificate of tabsira.me, www and api by HTTP
#      (webroot, behind a bootstrap server block), and the one of
#      admin.tabsira.me by a DNS-01 challenge (the admin host has no public
#      address), with a renewal hook that runs `nginx -t` before it reloads.
#   7. deploy/apply-config.sh: the nginx site and snippets, the systemd units
#      and timers, log rotation.
#   8. A narrow sudoers file and /usr/local/bin/tabsira-deploy, the launcher
#      Jenkins and the owners call.
#
# Usage (as root, from a checkout of the repository, on the application host):
#   APP_HOST_VPN_IP=<this host's Netbird address> CERTBOT_EMAIL=<address> \
#     CERTBOT_DNS_PLUGIN=<provider> CERTBOT_DNS_CREDENTIALS=<file> \
#     deploy/provision-app.sh [--dry-run] [--skip-tls]
#
# Environment: APP_HOST_VPN_IP (required), CERTBOT_EMAIL (required for TLS),
# CERTBOT_DNS_PLUGIN (the certbot DNS plugin of the DNS provider, for example
# the provider's name; required for the admin certificate),
# CERTBOT_DNS_CREDENTIALS (its credentials file, mode 0600, supplied by the
# owners, never in git), APP_USER (tabsira), APP_ROOT (/srv/tabsira), APP_REPO
# (git URL to clone on the first run), VPN_SUBNET, PG_CLIENT_VERSION (18).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"
# shellcheck disable=SC1091
source "$DEPLOY_DIR/net-lib.sh"

SKIP_TLS=false
for arg in "$@"; do
	case "$arg" in
	--dry-run) set_dry_run ;;
	--skip-tls) SKIP_TLS=true ;;
	*) die "usage: provision-app.sh [--dry-run] [--skip-tls]" ;;
	esac
done

APP_USER="${APP_USER:-tabsira}"
APP_REPO="${APP_REPO:-}"
PG_CLIENT_VERSION="${PG_CLIENT_VERSION:-18}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
CERTBOT_DNS_PLUGIN="${CERTBOT_DNS_PLUGIN:-}"
CERTBOT_DNS_CREDENTIALS="${CERTBOT_DNS_CREDENTIALS:-}"
TLS_NAMES=(tabsira.me www.tabsira.me api.tabsira.me)
ADMIN_NAME="admin.tabsira.me"
require_app_host

if is_dry; then
	banner "DRY RUN: application host"
	log "user          $APP_USER; layout $APP_ROOT/{repo,releases,shared,static}; logs /var/log/tabsira"
	log "packages      nginx certbot${CERTBOT_DNS_PLUGIN:+ python3-certbot-dns-$CERTBOT_DNS_PLUGIN} git curl postgresql-client-$PG_CLIENT_VERSION"
	log "node          latest 24.x from nodejs.org (sha256 verified), corepack pnpm, pm2, pm2 at boot for $APP_USER"
	log "uv, python    uv for $APP_USER; Python from apps/api/.python-version, uv-managed"
	log "env file      $APP_ROOT/shared/.env from deploy/env.production.example when missing (0600)"
	log "tls           ${TLS_NAMES[*]} by HTTP (webroot); $ADMIN_NAME by DNS-01 (plugin: ${CERTBOT_DNS_PLUGIN:-NOT SET})"
	log "config        deploy/apply-config.sh: nginx (nginx -t, restore on failure), systemd units (api, vision, scan worker) and timers, logrotate"
	log "sudoers       $APP_USER may restart tabsira-api, tabsira-vision and tabsira-worker, nothing else; launcher /usr/local/bin/tabsira-deploy"
	ok "Dry run complete: nothing was changed."
	exit 0
fi

[[ $EUID -eq 0 ]] || die "Run as root (sudo)."
require_ubuntu
export DEBIAN_FRONTEND=noninteractive
ip -4 addr show dev "${VPN_IFACE:-wt0}" >/dev/null 2>&1 ||
	warn "No ${VPN_IFACE:-wt0} interface: install and connect Netbird before the admin host and the database can be reached."

as_user() { sudo -u "$APP_USER" -H "$@"; }

# Production runs on UTC: logs, timers and the database agree whatever the admins' own zone.
[[ "$(timedatectl show -p Timezone --value 2>/dev/null || true)" == UTC ]] || timedatectl set-timezone UTC || true

# ─── 1. Packages ────────────────────────────────────────────────────
log "Installing packages"
apt-get update -qq
PACKAGES=(nginx certbot git curl ca-certificates gnupg openssl xz-utils build-essential)
[[ -z "$CERTBOT_DNS_PLUGIN" ]] || PACKAGES+=("python3-certbot-dns-$CERTBOT_DNS_PLUGIN")
apt-get install -y -qq "${PACKAGES[@]}" >/dev/null
if [[ ! -s /etc/apt/keyrings/postgresql.gpg ]]; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg
	chmod a+r /etc/apt/keyrings/postgresql.gpg
	echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt $OS_CODENAME-pgdg main" >/etc/apt/sources.list.d/pgdg.list
	apt-get update -qq
fi
apt-get install -y -qq "postgresql-client-$PG_CLIENT_VERSION" >/dev/null

# ─── 2. User and layout ─────────────────────────────────────────────
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"
APP_GROUP="$(id -gn "$APP_USER")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$APP_ROOT" "$APP_ROOT/releases" "$APP_ROOT/shared" \
	"$APP_ROOT/shared/state" "$APP_ROOT/shared/cache" "$APP_ROOT/shared/vision-weights"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0755 "$APP_ROOT/static" /var/log/tabsira
install -d -m 0755 /var/www/certbot /etc/tabsira
# nginx (www-data) reads the static files; it needs to traverse APP_ROOT.
chmod o+x "$APP_ROOT"
if [[ -n "$APP_REPO" && ! -d "$APP_ROOT/repo/.git" ]]; then
	log "Cloning the repository"
	as_user git clone "$APP_REPO" "$APP_ROOT/repo"
fi
cat >/etc/tabsira/deploy.env <<EOF
# Read by deploy/deploy.sh. No secret: addresses and names only.
APP_ROOT=$APP_ROOT
APP_HOST_VPN_IP=$APP_HOST_VPN_IP
VPN_SUBNET=${VPN_SUBNET:-100.64.0.0/10}
APP_USER=$APP_USER
EOF
chmod 0644 /etc/tabsira/deploy.env

# ─── 3. Node, pnpm, pm2 ─────────────────────────────────────────────
if ! have node || [[ "$(node -p 'process.versions.node.split(".")[0]')" -lt 24 ]]; then
	case "$(uname -m)" in
	x86_64 | amd64) NODE_ARCH=x64 ;;
	aarch64 | arm64) NODE_ARCH=arm64 ;;
	*) die "unsupported CPU: $(uname -m)" ;;
	esac
	NODE_BASE="https://nodejs.org/dist/latest-v24.x"
	SUMS="$(curl -fsSL "$NODE_BASE/SHASUMS256.txt")"
	NODE_FILE="$(awk -v a="linux-$NODE_ARCH.tar.xz" '$2 ~ a { print $2; exit }' <<<"$SUMS")"
	[[ -n "$NODE_FILE" ]] || die "No Node 24 build for linux-$NODE_ARCH on nodejs.org."
	log "Installing $NODE_FILE"
	TMP_NODE="$(mktemp -d)"
	curl -fsSL -o "$TMP_NODE/$NODE_FILE" "$NODE_BASE/$NODE_FILE"
	(cd "$TMP_NODE" && grep " $NODE_FILE\$" <<<"$SUMS" | sha256sum -c -) || die "Checksum of $NODE_FILE does not match."
	rm -rf /opt/node-24
	mkdir -p /opt/node-24
	tar -xJf "$TMP_NODE/$NODE_FILE" -C /opt/node-24 --strip-components=1
	rm -rf "$TMP_NODE"
	for bin in node npm npx corepack; do ln -sf "/opt/node-24/bin/$bin" "/usr/local/bin/$bin"; done
fi
corepack enable --install-directory /usr/local/bin
/opt/node-24/bin/npm install -g pm2 >/dev/null
ln -sf /opt/node-24/bin/pm2 /usr/local/bin/pm2
ok "node $(node -v), pm2 $(pm2 -v)"
env PATH="$PATH:/opt/node-24/bin" pm2 startup systemd -u "$APP_USER" --hp "$APP_HOME" >/dev/null
ok "pm2 starts at boot (pm2-$APP_USER.service)"

# ─── 4. uv and Python ───────────────────────────────────────────────
if ! as_user test -x "$APP_HOME/.local/bin/uv"; then
	log "Installing uv for $APP_USER"
	as_user env UV_NO_MODIFY_PATH=1 sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi
as_user env UV_PYTHON_PREFERENCE=only-managed "$APP_HOME/.local/bin/uv" python install "$(tr -d '[:space:]' <"$REPO_ROOT/apps/api/.python-version")"
ok "$(as_user "$APP_HOME/.local/bin/uv" --version)"

# ─── 5. Environment file ────────────────────────────────────────────
ENV_TARGET="$APP_ROOT/shared/.env"
if [[ ! -f "$ENV_TARGET" ]]; then
	install -o "$APP_USER" -g "$APP_GROUP" -m 0600 "$DEPLOY_DIR/env.production.example" "$ENV_TARGET"
	warn "Wrote $ENV_TARGET from the template: replace every CHANGE_ME and placeholder before the first deploy."
fi
if grep -q '^HASH_SECRET=CHANGE_ME' "$ENV_TARGET"; then
	secret="$(openssl rand -hex 32)"
	sed -i "s/^HASH_SECRET=CHANGE_ME.*/HASH_SECRET=$secret/" "$ENV_TARGET"
	ok "Generated HASH_SECRET in $ENV_TARGET"
fi

# ─── 6. TLS ─────────────────────────────────────────────────────────
issue_tls() {
	[[ -n "$CERTBOT_EMAIL" ]] || die "Set CERTBOT_EMAIL (or pass --skip-tls)."
	local domains=() name
	for name in "${TLS_NAMES[@]}"; do domains+=(-d "$name"); done
	# Reload only a configuration that passes nginx -t.
	install -D -m 0755 /dev/stdin /etc/letsencrypt/renewal-hooks/deploy/tabsira-nginx-reload.sh <<'HOOK'
#!/bin/sh
nginx -t && systemctl reload nginx
HOOK
	if [[ ! -s "/etc/letsencrypt/live/${TLS_NAMES[0]}/fullchain.pem" ]]; then
		log "Issuing the certificate of ${TLS_NAMES[*]} (HTTP challenge, behind a bootstrap block)"
		cat >/etc/nginx/conf.d/tabsira-bootstrap.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${TLS_NAMES[*]};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 404; }
}
EOF
		nginx -t && systemctl reload nginx
		certbot certonly --webroot -w /var/www/certbot "${domains[@]}" \
			--email "$CERTBOT_EMAIL" --agree-tos --non-interactive --no-eff-email || {
			rm -f /etc/nginx/conf.d/tabsira-bootstrap.conf
			die "certbot could not issue the certificate. The names must resolve to this host's public address."
		}
		rm -f /etc/nginx/conf.d/tabsira-bootstrap.conf
	fi
	if [[ ! -s "/etc/letsencrypt/live/$ADMIN_NAME/fullchain.pem" ]]; then
		[[ -n "$CERTBOT_DNS_PLUGIN" && -f "$CERTBOT_DNS_CREDENTIALS" ]] ||
			die "The admin certificate needs a DNS challenge: set CERTBOT_DNS_PLUGIN and CERTBOT_DNS_CREDENTIALS (a 0600 file the owners supply)."
		chmod 0600 "$CERTBOT_DNS_CREDENTIALS"
		log "Issuing the certificate of $ADMIN_NAME (DNS-01, plugin $CERTBOT_DNS_PLUGIN)"
		certbot certonly "--dns-$CERTBOT_DNS_PLUGIN" "--dns-$CERTBOT_DNS_PLUGIN-credentials" "$CERTBOT_DNS_CREDENTIALS" \
			-d "$ADMIN_NAME" --email "$CERTBOT_EMAIL" --agree-tos --non-interactive --no-eff-email
	fi
	systemctl enable --now certbot.timer >/dev/null 2>&1 || true
}
if $SKIP_TLS; then
	warn "--skip-tls: no certificate issued; deploy/apply-config.sh refuses to run without one."
else
	issue_tls
fi

# ─── 7. nginx, units, log rotation ──────────────────────────────────
if ! $SKIP_TLS; then
	APP_USER="$APP_USER" APP_GROUP="$APP_GROUP" APP_HOME="$APP_HOME" bash "$DEPLOY_DIR/apply-config.sh"
fi

# ─── 8. sudoers and the launcher ────────────────────────────────────
SUDOERS_TMP="$(mktemp)"
sed "s#@APP_USER@#$APP_USER#g" "$DEPLOY_DIR/sudoers/tabsira" >"$SUDOERS_TMP"
visudo -cf "$SUDOERS_TMP" >/dev/null || die "The sudoers file does not parse; nothing installed."
install -m 0440 "$SUDOERS_TMP" /etc/sudoers.d/tabsira
rm -f "$SUDOERS_TMP"
# The launcher is root-owned and small, so it does not change with the
# repository: it brings the clone to the commit, then runs that commit's deploy.
cat >/usr/local/bin/tabsira-deploy <<EOF
#!/usr/bin/env bash
# Installed by deploy/provision-app.sh. Usage: tabsira-deploy [--ref REF] [--dry-run] | --rollback
set -Eeuo pipefail
cd "$APP_ROOT/repo"
ref=origin/main
args=("\$@")
for ((i = 0; i < \${#args[@]}; i++)); do
	[[ "\${args[i]}" == "--ref" ]] && ref="\${args[i + 1]:-origin/main}"
done
if [[ " \$* " != *" --rollback "* ]]; then
	git fetch --prune origin
	git checkout --detach "\$(git rev-parse --verify "\$ref^{commit}")"
fi
exec bash deploy/deploy.sh "\$@"
EOF
chmod 0755 /usr/local/bin/tabsira-deploy

ok "Application host provisioned. Next: fill $ENV_TARGET, then as $APP_USER: tabsira-deploy --dry-run, then tabsira-deploy"
