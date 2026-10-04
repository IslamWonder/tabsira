#!/usr/bin/env bash
# Read-only readiness check of the application host and its environment file, in
# plain shell: it needs no release and no Python environment, so it can run before
# the first deploy. Nothing is installed, written or restarted.
#
#   cd /opt/tabsira && ./deploy/deploy.sh --check      (also: deploy/check.sh)
#
# Run it as the application user (devops). Everything is readable to that user
# except the Let's Encrypt certificates, which are root only: those are read with
# `sudo -n` when that needs no password, and otherwise reported as "run with sudo".
# Run with sudo, it checks the user's part as that user (SUDO_USER: its PATH, its
# nvm) and the certificates as root, so both runs say the same thing.
#
# Every line is `ok`, `fix` (required: the exit status is 1) or `check`
# (recommended). Secrets are never printed, only whether they are set. Once a
# release exists, `python -m src.cli.check_config --live` (docs/OPERATIONS.md,
# "Checking the environment file") goes further and tries each service for real.
#
# Environment: REPO_DIR (/opt/tabsira), APP_ROOT (/srv/tabsira), ENV_FILE
# (/opt/tabsira/.env), LE_DIR (/etc/letsencrypt/live),
# TLS_NAME, API_TLS_NAME, ADMIN_TLS_NAME, TLS_WARN_DAYS (30); /etc/tabsira/deploy.env
# is read first when present.

set -Eeuo pipefail
# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/lib.sh"

DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE:-/etc/tabsira/deploy.env}"
if [[ -f "$DEPLOY_ENV_FILE" ]]; then
	set -a
	# shellcheck disable=SC1090
	. "$DEPLOY_ENV_FILE"
	set +a
fi
APP_ROOT="${APP_ROOT:-/srv/tabsira}"
REPO_DIR="${REPO_DIR:-/opt/tabsira}"
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
APP_USER="${APP_USER:-devops}"
# all | user (host, clone, environment file, data stores) | certs (root only)
CHECK_PART="${CHECK_PART:-all}"
LE_DIR="${LE_DIR:-/etc/letsencrypt/live}"
TLS_NAME="${TLS_NAME:-tabsira.me}"
API_TLS_NAME="${API_TLS_NAME:-api.tabsira.me}"
ADMIN_TLS_NAME="${ADMIN_TLS_NAME:-admin.tabsira.me}"
TLS_WARN_DAYS="${TLS_WARN_DAYS:-30}"
FIXES=0
WARNINGS=0

# line LEVEL STATUS NAME [DETAIL]: LEVEL is fix | check; STATUS is ok | bad.
line() {
	local level="$1" status="$2" name="$3" detail="${4:-}" mark
	if [[ "$status" == ok ]]; then
		mark="${C_GREEN}ok    ${C_RESET}"
	elif [[ "$level" == fix ]]; then
		mark="${C_RED}fix   ${C_RESET}"
		FIXES=$((FIXES + 1))
	else
		mark="${C_YELLOW}check ${C_RESET}"
		WARNINGS=$((WARNINGS + 1))
	fi
	printf '  %s %s%s\n' "$mark" "$name" "${detail:+  ($detail)}"
}
# test LEVEL NAME DETAIL CMD...: ok when the command succeeds.
test_that() {
	local level="$1" name="$2" detail="$3"
	shift 3
	if "$@" >/dev/null 2>&1; then line "$level" ok "$name"; else line "$level" bad "$name" "$detail"; fi
}
section() { printf '\n%s\n' "${C_BOLD}$1${C_RESET}"; }
val() { env_get "$ENV_FILE" "$1"; }
no_dev_address() {
	# The development top-level domain, spelled in two parts so no production file contains it.
	local dev_tld="te""st"
	! grep -Eq "^[A-Za-z_]+=.*[a-z0-9-]\\.${dev_tld}([/:\"' ]|\$)" "$ENV_FILE"
}
is_https() { [[ "$1" == https://* ]]; }
at_least() { (($1 >= $2)); }
reachable() { timeout 5 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null; }
host_of() { sed -E 's#^[a-z+]+://([^@/]*@)?(\[[^]]+\]|[^:/]+).*#\2#' <<<"$1"; }
port_of() { sed -nE 's#^[a-z+]+://([^@/]*@)?(\[[^]]+\]|[^:/]+):([0-9]+).*#\3#p' <<<"$1"; }

TOOL_HINT_USER="run sudo deploy/provision-app.sh (it runs deploy/install-toolchain.sh as $APP_USER: nvm, Node, pnpm, pm2, uv)"
TOOL_HINT_SYSTEM="run sudo deploy/provision-app.sh (apt packages)"

check_user_part() {
	section "Host"
	line check ok "running as $(id -un) on $(hostname)"
	for tool in git curl openssl psql; do
		test_that fix "$tool is installed" "$TOOL_HINT_SYSTEM" have "$tool"
	done
	for tool in node pnpm pm2 uv; do
		test_that fix "$tool is on the PATH of $(id -un)" "$TOOL_HINT_USER" have "$tool"
	done
	if have node; then
		want="$(tr -d '[:space:]' <"$REPO_ROOT/.nvmrc")"
		test_that fix "Node major is $want (.nvmrc)" "node $(node --version)" test "$(node -p 'process.versions.node.split(".")[0]')" = "$want"
	fi

	section "Clone ($REPO_DIR)"
	test_that fix "$REPO_DIR is a git clone" "git clone <repository> $REPO_DIR" test -d "$REPO_DIR/.git"
	test_that fix "$REPO_DIR is writable by $(id -un)" "sudo chown -R $(id -un): $REPO_DIR" test -w "$REPO_DIR"
	test_that fix "the clone tracks an upstream branch" "git -C $REPO_DIR branch --set-upstream-to=origin/main" git -C "$REPO_DIR" rev-parse --verify -q '@{u}'
	test_that check "the clone has no local changes" "a deploy resets it to its upstream branch" git -C "$REPO_DIR" diff --quiet HEAD
	test_that fix ".env is ignored by git" "it must never be committed" git -C "$REPO_DIR" check-ignore -q .env

	section "Runtime ($APP_ROOT)"
	for dir in releases shared shared/state shared/cache shared/vision-weights shared/corpus shared/vectors static; do
		test_that fix "$APP_ROOT/$dir exists and is writable" "sudo deploy/provision-app.sh creates the layout" test -w "$APP_ROOT/$dir"
	done
	test_that fix "/etc/tabsira/deploy.env exists" "written by deploy/provision-app.sh" test -f "$DEPLOY_ENV_FILE"
	test_that check "/var/log/tabsira is writable" "pm2 writes the web logs there" test -w /var/log/tabsira
	for unit in "$API_UNIT" "$WORKER_UNIT" "$VISION_UNIT"; do
		test_that fix "$unit is installed" "sudo deploy/apply-config.sh" test -f "/etc/systemd/system/$unit"
	done
	test_that fix "sudoers lets this user restart the units" "installed by deploy/provision-app.sh" test -f /etc/sudoers.d/tabsira
	test_that check "the nginx site is enabled" "sudo deploy/apply-config.sh" test -L /etc/nginx/sites-enabled/tabsira
	test_that check "the host configuration matches this checkout" "sudo deploy/apply-config.sh --check lists what differs" \
		bash "$DEPLOY_DIR/apply-config.sh" --check

	section "Environment file ($ENV_FILE)"
	if [[ ! -f "$ENV_FILE" ]]; then
		line fix bad "the file exists" "copy deploy/env.production.example there, mode 0600"
	else
		line fix ok "the file exists"
		mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE")"
		test_that fix "mode is 600" "now $mode: chmod 600" test "$mode" = 600
		test_that fix "ENVIRONMENT=production" "now '$(val ENVIRONMENT)'" test "$(val ENVIRONMENT)" = production
		placeholders="$(grep -nE 'CHANGE_ME|DATA_HOST_VPN_IP|APP_HOST_VPN_IP' "$ENV_FILE" | cut -d: -f1 | paste -sd, - || true)"
		test_that fix "no placeholder left" "lines $placeholders" test -z "$placeholders"
		test_that fix "no development address" "the file names a development host" no_dev_address
		for key in DATABASE_URL SYNC_DATABASE_URL REDIS_URL REDIS_PASSWORD HASH_SECRET ADMIN_TOTP_ENCRYPTION_KEY \
			SITE_URL API_URL ADMIN_URL CORS_ORIGINS SESSION_COOKIE_DOMAIN \
			S3_BUCKET S3_ACCESS_KEY_ID S3_SECRET_ACCESS_KEY S3_PUBLIC_BASE_URL; do
			test_that fix "$key is set" "empty or missing" test -n "$(val "$key")"
		done
		provider="$(val AI_PROVIDER)"
		provider="${provider:-openai}"
		case "$provider" in
		openai) ai_key="AI_OPENAI__API_KEY" ;;
		ovh) ai_key="AI_OVH__API_KEY" ;;
		*) ai_key="" ;;
		esac
		if [[ -z "$ai_key" ]]; then
			line fix bad "AI_PROVIDER is openai or ovh" "now '$provider'"
		else
			test_that fix "$ai_key is set (AI_PROVIDER=$provider)" "empty or missing" test -n "$(val "$ai_key")"
		fi
		for key in SITE_URL API_URL ADMIN_URL; do
			test_that fix "$key is https" "now '$(val "$key")'" is_https "$(val "$key")"
		done
		secret="$(val HASH_SECRET)"
		test_that fix "HASH_SECRET is 32+ characters" "too short" at_least "${#secret}" 32
		test_that fix "STORAGE_BACKEND is s3" "now '$(val STORAGE_BACKEND)'" test "$(val STORAGE_BACKEND)" = s3
		test_that check "SMTP_HOST is set" "without it no verification or reset mail is sent" test -n "$(val SMTP_HOST)"
		test_that check "ADMIN_REQUIRE_TWO_FACTOR=true" "once the first admin has enrolled" test "$(val ADMIN_REQUIRE_TWO_FACTOR)" = true
		test_that check "GLITCHTIP_DSN is set" "error reports" test -n "$(val GLITCHTIP_DSN)"

		section "Database and Redis"
		for pair in "DATABASE_URL:5432" "REDIS_URL:6379"; do
			key="${pair%%:*}"
			url="$(val "$key")"
			host="$(host_of "$url")"
			port="$(port_of "$url")"
			port="${port:-${pair##*:}}"
			if [[ -n "$host" ]]; then
				test_that fix "$key: $host:$port accepts connections" "is the VPN up, and does the data host allow this one?" reachable "$host" "$port"
			fi
		done
		sync_url="$(val SYNC_DATABASE_URL | sed -E 's#^postgresql\+[a-z]+:#postgresql:#')"
		if [[ -n "$sync_url" ]] && have psql; then
			test_that fix "the database accepts this login" "psql SELECT 1 failed" psql -X -q -tA "$sync_url" -c 'select 1'
		fi
	fi
}

check_certs() {
	section "Certificates (Let's Encrypt)"
	for name in "$TLS_NAME" "$API_TLS_NAME" "$ADMIN_TLS_NAME"; do
		cert="$LE_DIR/$name/fullchain.pem"
		if [[ ! -r "$cert" ]]; then
			line fix bad "$name has a certificate" "no readable $cert: certbot certonly --cert-name $name -d $name"
			continue
		fi
		line fix ok "$name has a certificate"
		test_that check "$name is valid for $TLS_WARN_DAYS more days" "renew it: certbot renew" openssl x509 -in "$cert" -noout -checkend $((TLS_WARN_DAYS * 86400))
		test_that fix "$name's certificate names $name" "wrong certificate" bash -c "openssl x509 -in '$cert' -noout -ext subjectAltName | grep -q 'DNS:$name'"
		test_that check "$name renews through the webroot" "certbot reconfigure --cert-name $name --authenticator webroot --webroot-path /var/www/certbot --installer none" \
			bash -c "! grep -q '^authenticator = nginx' '/etc/letsencrypt/renewal/$name.conf'"
	done
	test_that check "www.$TLS_NAME is on the $TLS_NAME certificate" "certbot certonly --cert-name $TLS_NAME -d $TLS_NAME -d www.$TLS_NAME --expand" \
		bash -c "openssl x509 -in '$LE_DIR/$TLS_NAME/fullchain.pem' -noout -ext subjectAltName | grep -q 'DNS:www.$TLS_NAME'"
}

# Print the lines of a part run elsewhere and add its counts (its last line is "#counts F W").
merge() {
	local output="$1" counts
	counts="$(tail -n 1 <<<"$output")"
	sed '$d' <<<"$output"
	if [[ "$counts" =~ ^\#counts\ ([0-9]+)\ ([0-9]+)$ ]]; then
		FIXES=$((FIXES + BASH_REMATCH[1]))
		WARNINGS=$((WARNINGS + BASH_REMATCH[2]))
	fi
}

case "$CHECK_PART" in
user)
	check_user_part
	printf '#counts %s %s\n' "$FIXES" "$WARNINGS"
	exit 0
	;;
certs)
	check_certs
	printf '#counts %s %s\n' "$FIXES" "$WARNINGS"
	exit 0
	;;
esac

if [[ $EUID -eq 0 ]]; then
	# The user's part as that user: root has neither its PATH nor its nvm.
	run_as="${SUDO_USER:-$APP_USER}"
	[[ "$run_as" != root ]] || run_as="$APP_USER"
	id -u "$run_as" >/dev/null 2>&1 || die "No user $run_as: set APP_USER."
	merge "$(cd / && sudo -u "$run_as" -H env CHECK_PART=user DEPLOY_ENV_FILE="$DEPLOY_ENV_FILE" bash "$DEPLOY_DIR/check.sh" 2>&1 || true)"
	check_certs
elif [[ -r "$LE_DIR/$TLS_NAME/fullchain.pem" ]]; then
	check_user_part
	check_certs
else
	check_user_part
	if sudo -n true 2>/dev/null; then
		merge "$(sudo -n env CHECK_PART=certs bash "$DEPLOY_DIR/check.sh" 2>&1 || true)"
	else
		section "Certificates (Let's Encrypt)"
		line check bad "the certificates are readable by root only" "run sudo ./deploy/deploy.sh --check to check them too"
	fi
fi

printf '\n'
if ((FIXES > 0)); then
	err "$FIXES required item(s) to fix, $WARNINGS to check."
	exit 1
fi
ok "Nothing required to fix. $WARNINGS item(s) to check."
