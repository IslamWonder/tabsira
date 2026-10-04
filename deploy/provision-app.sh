#!/usr/bin/env bash
# Provision the production APPLICATION host (Ubuntu 24.04 or 26.04): the account the
# application runs as (devops), nvm with Node, pnpm and pm2, uv and Python, nginx
# with HTTPS from certbot, the systemd units, log rotation and the layout
# deploy/deploy.sh expects: the git clone at /opt/tabsira with its .env, as on the
# earlier prototype, and the releases under /srv/tabsira. No Docker.
#
# What it does, in order:
#   1. apt packages: nginx, certbot (and its DNS plugin), git, curl,
#      postgresql-client-18 from PGDG (psql and pg_dump for migrations and dumps).
#   2. The application user and the layout: the clone at REPO_DIR (/opt/tabsira,
#      cloned from APP_REPO when it is not there yet) which the API, the scan worker
#      and vision run from in place; /srv/tabsira/web for the web builds and
#      /srv/tabsira/static for their static files, as on the earlier prototype;
#      /var/log/tabsira.
#   3. The toolchain, in the application user's home (deploy/install-toolchain.sh):
#      nvm with the Node of .nvmrc, the pnpm package.json pins, pm2, uv and the
#      Python apps/api/.python-version names as uv builds it (never the system
#      Python); pm2 starts at boot for the application user.
#   5. The production environment file, REPO_DIR/.env, from deploy/env.production.example, only
#      when none exists (mode 0600); HASH_SECRET is generated when still a
#      placeholder. Every other CHANGE_ME stays for the owners.
#   6. TLS: one certbot lineage per name (tabsira.me with www, api.tabsira.me,
#      admin.tabsira.me), each by an HTTP challenge through the webroot; existing
#      lineages are kept and moved to webroot renewal; a renewal hook runs
#      `nginx -t` before it reloads.
#   7. deploy/apply-config.sh: the nginx site and snippets, the systemd units
#      and timers, log rotation.
#   8. A narrow sudoers file and /usr/local/bin/tabsira-deploy, the launcher
#      Jenkins and the owners call.
#
# Usage (as root, from a checkout of the repository, on the application host):
#   CERTBOT_EMAIL=<address> \
#     deploy/provision-app.sh [--dry-run | --check] [--skip-tls]
#
# Environment: APP_HOST_VPN_IP (default: this host's address on wt0, found by itself), CERTBOT_EMAIL (required for TLS),
# CERTBOT_DNS_PLUGIN and CERTBOT_DNS_CREDENTIALS (optional: issue the admin
# certificate by DNS-01 instead of HTTP; the credentials file is mode 0600, supplied
# by the owners, never in git), APP_USER (the account that ran sudo, else devops;
# created when missing), REPO_DIR (/opt/tabsira), WEB_RELEASES_DIR (/srv/tabsira/web), STATIC_DIR
# (/srv/tabsira/static), APP_REPO (git URL to clone
# into REPO_DIR when it is not a clone yet), VPN_SUBNET, PG_CLIENT_VERSION (18).

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"
# shellcheck disable=SC1091
source "$DEPLOY_DIR/net-lib.sh"

SKIP_TLS=false
for arg in "$@"; do
	case "$arg" in
	--dry-run | --check) set_dry_run ;;
	--skip-tls) SKIP_TLS=true ;;
	*) die "usage: provision-app.sh [--dry-run | --check] [--skip-tls]" ;;
	esac
done

# The account that ran sudo (devops), never root: the application runs as an existing user, as on the earlier prototype.
APP_USER="${APP_USER:-${SUDO_USER:-devops}}"
[[ "$APP_USER" != "root" ]] || APP_USER=devops
APP_REPO="${APP_REPO:-}"
PG_CLIENT_VERSION="${PG_CLIENT_VERSION:-18}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
CERTBOT_DNS_PLUGIN="${CERTBOT_DNS_PLUGIN:-}"
CERTBOT_DNS_CREDENTIALS="${CERTBOT_DNS_CREDENTIALS:-}"
WEB_NAME="${TLS_NAME:-tabsira.me}"
API_NAME="${API_TLS_NAME:-api.tabsira.me}"
ADMIN_NAME="${ADMIN_TLS_NAME:-admin.tabsira.me}"
detect_app_host

if is_dry; then
	banner "DRY RUN: application host"
	log "user          $APP_USER; clone $REPO_DIR (with its .env); web builds $WEB_RELEASES_DIR; static $STATIC_DIR; logs /var/log/tabsira"
	log "packages      nginx certbot${CERTBOT_DNS_PLUGIN:+ python3-certbot-dns-$CERTBOT_DNS_PLUGIN} git curl postgresql-client-$PG_CLIENT_VERSION"
	log "toolchain     deploy/install-toolchain.sh as $APP_USER: nvm, Node (.nvmrc), pnpm (package.json), pm2, uv, Python (apps/api/.python-version); pm2 at boot"
	log "env file      $ENV_FILE from deploy/env.production.example when missing (0600)"
	log "tls           one certbot lineage each: $WEB_NAME (+www), $API_NAME, $ADMIN_NAME, by HTTP through the webroot${CERTBOT_DNS_PLUGIN:+ ($ADMIN_NAME by DNS-01, plugin $CERTBOT_DNS_PLUGIN)}; existing lineages kept, nginx-plugin renewals moved to the webroot"
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
id -u "$APP_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$APP_USER"
APP_GROUP="$(id -gn "$APP_USER")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$WEB_RELEASES_DIR" "$WEB_RELEASES_DIR/releases"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0755 "$(dirname "$STATIC_DIR")" "$STATIC_DIR" /var/log/tabsira
install -d -m 0755 /var/www/certbot /etc/tabsira
# nginx (www-data) reads the static files; it needs to traverse their parent.
chmod o+x "$(dirname "$STATIC_DIR")"
if [[ ! -d "$REPO_DIR/.git" ]]; then
	[[ -n "$APP_REPO" ]] || die "$REPO_DIR is not a git clone. Clone the repository there first, or set APP_REPO."
	log "Cloning the repository into $REPO_DIR"
	install -d -o "$APP_USER" -g "$APP_GROUP" -m 0755 "$REPO_DIR"
	as_user git clone "$APP_REPO" "$REPO_DIR"
fi
[[ "$(stat -c %U "$REPO_DIR")" == "$APP_USER" ]] || chown -R "$APP_USER:$APP_GROUP" "$REPO_DIR"
[[ "$(cd "$REPO_ROOT" && pwd -P)" == "$(cd "$REPO_DIR" && pwd -P)" ]] ||
	warn "This script runs from $REPO_ROOT, not from the clone $REPO_DIR; deploys run from $REPO_DIR."
cat >/etc/tabsira/deploy.env <<EOF
# Read by deploy/deploy.sh and deploy/check.sh. No secret: addresses and names only.
REPO_DIR=$REPO_DIR
ENV_FILE=$ENV_FILE
WEB_RELEASES_DIR=$WEB_RELEASES_DIR
STATIC_DIR=$STATIC_DIR
APP_HOST_VPN_IP=$APP_HOST_VPN_IP
VPN_SUBNET=${VPN_SUBNET:-100.64.0.0/10}
APP_USER=$APP_USER
EOF
chmod 0644 /etc/tabsira/deploy.env

# ─── 3. Toolchain: nvm, Node, pnpm, pm2, uv, Python ─────────────────
# Installed in the application user's home by deploy/install-toolchain.sh (pinned
# versions, no rc file edited), then pm2 is registered with systemd for that user.
as_user bash "$DEPLOY_DIR/install-toolchain.sh"
# shellcheck disable=SC2016  # expanded by the application user's shell
NODE_BIN="$(as_user bash -c 'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" --no-use; nvm use --silent default; dirname "$(command -v node)"')"
[[ -x "$NODE_BIN/pm2" ]] || die "pm2 is not in $NODE_BIN."
env PATH="$PATH:$NODE_BIN" "$NODE_BIN/pm2" startup systemd -u "$APP_USER" --hp "$APP_HOME" >/dev/null
ok "pm2 starts at boot (pm2-$APP_USER.service)"

# ─── 5. Environment file ────────────────────────────────────────────
ENV_TARGET="$ENV_FILE"
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
# One certbot lineage per name: tabsira.me (with www), api.tabsira.me and
# admin.tabsira.me, each by an HTTP challenge through the webroot, so renewals need
# no nginx plugin and no DNS credential. A lineage that already exists is left alone
# (but moved to webroot renewal when certbot --nginx made it). The admin name needs
# a public A record for the challenge; nginx still serves the admin area on the VPN
# address only. CERTBOT_DNS_PLUGIN and CERTBOT_DNS_CREDENTIALS issue the admin
# certificate by DNS-01 instead, for a host with no public record.
issue_lineage() {
	local name="$1"
	shift
	[[ ! -s "/etc/letsencrypt/live/$name/fullchain.pem" ]] || return 0
	log "Issuing the certificate of $name"
	certbot certonly --cert-name "$name" "$@" --email "$CERTBOT_EMAIL" --agree-tos --non-interactive --no-eff-email ||
		die "certbot could not issue the certificate of $name. Its names must resolve to this host's public address."
}

issue_tls() {
	[[ -n "$CERTBOT_EMAIL" ]] || die "Set CERTBOT_EMAIL (or pass --skip-tls)."
	# Reload only a configuration that passes nginx -t.
	install -D -m 0755 /dev/stdin /etc/letsencrypt/renewal-hooks/deploy/tabsira-nginx-reload.sh <<'HOOK'
#!/bin/sh
nginx -t && systemctl reload nginx
HOOK
	local webroot=(--webroot -w /var/www/certbot) name
	if [[ ! -s "/etc/letsencrypt/live/$WEB_NAME/fullchain.pem" || ! -s "/etc/letsencrypt/live/$API_NAME/fullchain.pem" ||
		(-z "$CERTBOT_DNS_PLUGIN" && ! -s "/etc/letsencrypt/live/$ADMIN_NAME/fullchain.pem") ]]; then
		# Nothing else answers port 80 yet: a bootstrap block serves the challenge files.
		cat >/etc/nginx/conf.d/tabsira-bootstrap.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $WEB_NAME www.$WEB_NAME $API_NAME $ADMIN_NAME;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 404; }
}
EOF
		nginx -t && systemctl reload nginx
		trap 'rm -f /etc/nginx/conf.d/tabsira-bootstrap.conf' RETURN
		issue_lineage "$WEB_NAME" "${webroot[@]}" -d "$WEB_NAME" -d "www.$WEB_NAME"
		issue_lineage "$API_NAME" "${webroot[@]}" -d "$API_NAME"
		if [[ -z "$CERTBOT_DNS_PLUGIN" ]]; then
			issue_lineage "$ADMIN_NAME" "${webroot[@]}" -d "$ADMIN_NAME"
		fi
	fi
	if [[ -n "$CERTBOT_DNS_PLUGIN" ]]; then
		[[ -f "$CERTBOT_DNS_CREDENTIALS" ]] || die "CERTBOT_DNS_PLUGIN is set: give CERTBOT_DNS_CREDENTIALS, a 0600 file the owners supply."
		chmod 0600 "$CERTBOT_DNS_CREDENTIALS"
		issue_lineage "$ADMIN_NAME" "--dns-$CERTBOT_DNS_PLUGIN" "--dns-$CERTBOT_DNS_PLUGIN-credentials" "$CERTBOT_DNS_CREDENTIALS" -d "$ADMIN_NAME"
	fi
	# Lineages made with `certbot --nginx` renew through the nginx plugin, which edits the live
	# configuration and cannot find the admin name. Renew them through the webroot instead.
	for name in "$WEB_NAME" "$API_NAME" "$ADMIN_NAME"; do
		if grep -q '^authenticator = nginx' "/etc/letsencrypt/renewal/$name.conf" 2>/dev/null; then
			log "Moving the renewal of $name to the webroot"
			certbot reconfigure --cert-name "$name" --authenticator webroot --webroot-path /var/www/certbot \
				--installer none --non-interactive >/dev/null
		fi
	done
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
# The launcher Jenkins calls over ssh: the clone's own deploy, which brings the
# clone up to date itself (deploy/deploy.sh), as `cd /opt/tabsira && ./deploy/deploy.sh` does.
cat >/usr/local/bin/tabsira-deploy <<EOF
#!/usr/bin/env bash
# Installed by deploy/provision-app.sh. Usage: tabsira-deploy [--ref REF] [--dry-run] | --rollback | --check
set -Eeuo pipefail
cd "$REPO_DIR"
exec bash deploy/deploy.sh "\$@"
EOF
chmod 0755 /usr/local/bin/tabsira-deploy

ok "Application host provisioned. Next, as $APP_USER in $REPO_DIR: fill .env, then ./deploy/deploy.sh --check, ./deploy/deploy.sh --dry-run, ./deploy/deploy.sh"
