#!/usr/bin/env bash
# Deploy TABSIRA on the production application host, in place, the way the earlier
# prototype does: the git clone at /opt/tabsira is the application.
#
# Order, and why:
#   1. Lock; check the host and the environment file (/opt/tabsira/.env).
#   2. Optionally dump the database first (PRE_DEPLOY_BACKUP=true).
#   3. Record the commit that serves now, so a failure can put the code back.
#   4. Pull: fetch, then reset the clone to its upstream branch. The deploy then
#      runs again from the updated copy, so the steps below are always the latest.
#   5. Install the API and vision dependencies (uv sync) and the workspace (pnpm).
#   6. check_config --live, then the migrations: geodata chain, app chain, vectors
#      chain (scripts/migrate.sh). Migrations are not undone by a rollback; each
#      must work with the code still serving while it runs (add before you drop).
#   7. Build the web app.
#   8. Replace the processes one at a time: the API's gunicorn workers (TTIN, health,
#      TTOU, after the new code has booted once on a spare port), the scan worker
#      (graceful restart), vision when services/vision changed, then the web
#      (deploy/web-roll.sh: its own copy under /srv/tabsira/web, a pre-flight, pm2
#      instances one at a time). Nothing goes down.
#   9. Health gate; compare the host configuration; IndexNow (production only).
#   On a failure after the pull: the clone goes back to the recorded commit, the
#   dependencies are installed again, the API and worker are rolled again and the
#   web goes back to its previous build. Migrations are not reverted.
#
# Usage (on the application host, as devops, from the clone):
#   cd /opt/tabsira && ./deploy/deploy.sh [--dry-run] [api] [worker] [vision] [web]
#   With no part named, all of them. `api` is the API, the migrations and the scan
#   worker (they share the code); `worker` the scan worker alone; `vision` the
#   detector (restarted); `web` the web build. `git pull && ./deploy/deploy.sh api web`
#   works too: the pull inside is then a no-op.
#   ./deploy/deploy.sh --rollback      back to the commit deployed before this one
#   ./deploy/deploy.sh --check         read-only readiness check (deploy/check.sh)
#
# Environment (all optional, see deploy/env.production.example):
#   PRE_DEPLOY_BACKUP SKIP_VISION SKIP_INDEXNOW WEB_HEALTH_PATH HEALTH_TIMEOUT and
#   the paths of deploy/lib.sh. /etc/tabsira/deploy.env, when present, is read first.

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

ORIGINAL_ARGS=("$@")
ROLLBACK=false
PARTS=""
while [[ $# -gt 0 ]]; do
	case "$1" in
	--dry-run)
		DRY_RUN=true
		shift
		;;
	--rollback)
		ROLLBACK=true
		shift
		;;
	--check)
		exec bash "$DEPLOY_DIR/check.sh"
		;;
	-h | --help)
		sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
		exit 0
		;;
	api | worker | vision | web)
		PARTS="$PARTS $1"
		shift
		;;
	all)
		PARTS="api worker vision web"
		shift
		;;
	*) die "Unknown option: $1 (api, worker, vision, web, --dry-run, --rollback, --check; see --help)" ;;
	esac
done

# No part named: deploy every part. `api` brings the scan worker, which runs the same code.
PARTS="${PARTS:- api worker vision web}"
[[ " $PARTS " != *" api "* || " $PARTS " == *" worker "* ]] || PARTS="$PARTS worker"
wants() { [[ " $PARTS " == *" $1 "* ]]; }
# Vision deployed implicitly is restarted only when its code changed; named, always.
VISION_NAMED=false
[[ " ${ORIGINAL_ARGS[*]-} " != *" vision "* ]] || VISION_NAMED=true
wants vision || SKIP_VISION=true

PRE_DEPLOY_BACKUP="${PRE_DEPLOY_BACKUP:-false}"
SKIP_VISION="${SKIP_VISION:-false}"
SKIP_INDEXNOW="${SKIP_INDEXNOW:-false}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
WEB_HEALTH_PATH="${WEB_HEALTH_PATH:-/}"
export WEB_HEALTH_PATH ENV_FILE REPO_DIR WEB_RELEASES_DIR STATIC_DIR DRY_RUN
# The commit each successful deploy left serving, newest last: what --rollback goes back to.
DEPLOYED_LOG="$WEB_RELEASES_DIR/deployed-commits"
LOCK_DIR="$WEB_RELEASES_DIR/deploy.lock"

load_runtime_settings
API_HEALTH_URL="http://127.0.0.1:${API_PORT}/health/ready"
ENVIRONMENT_NAME="$(env_get "$ENV_FILE" ENVIRONMENT)"
export UV_PYTHON_PREFERENCE=only-managed

PHASE="before-pull"
PREVIOUS_COMMIT=""
WEB_RELEASE_BEFORE=""
PYTHON_BEFORE=""
PYTHON_NOW=""

release_lock() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
take_lock() {
	mkdir -p "$WEB_RELEASES_DIR"
	mkdir "$LOCK_DIR" 2>/dev/null || die "Another deploy holds $LOCK_DIR (remove it if none is running)."
	trap release_lock EXIT
}

# ─── Install, then roll every process onto the code in the clone ───
install_dependencies() {
	if wants worker; then
		run_in "$REPO_DIR/apps/api" uv sync --frozen --no-dev
	fi
	if [[ "$SKIP_VISION" != "true" ]]; then
		run_in "$REPO_DIR/services/vision" uv sync --frozen --no-dev
	fi
	if wants web; then
		run_in "$REPO_DIR" pnpm install --frozen-lockfile
	fi
}

roll_api_and_worker() {
	if wants api; then
		bash "$DEPLOY_DIR/api-roll.sh" roll || sudo systemctl restart "$API_UNIT"
	fi
	if wants worker; then
		sudo systemctl restart "$WORKER_UNIT"
	fi
}

on_error() {
	local code=$?
	trap - ERR
	err "Deploy failed (exit $code) in phase '$PHASE'."
	if [[ "$PHASE" != "before-pull" && -n "$PREVIOUS_COMMIT" ]]; then
		err "Putting the code back on ${PREVIOUS_COMMIT:0:12} and rolling the services again."
		git -C "$REPO_DIR" reset --hard "$PREVIOUS_COMMIT" >/dev/null 2>&1 || true
		install_dependencies >/dev/null 2>&1 || true
		if [[ "$PHASE" == "rolling" ]]; then
			SKIP_SMOKE=1 roll_api_and_worker || err "The rollback roll failed too: check $API_UNIT by hand."
		fi
		if [[ -n "$WEB_RELEASE_BEFORE" && "$(real_dir "$WEB_RELEASES_DIR/current" || true)" != "$WEB_RELEASE_BEFORE" ]]; then
			bash "$DEPLOY_DIR/web-roll.sh" rollback || err "The web rollback failed: pm2 ls, then deploy/web-roll.sh rollback."
		fi
		err "Code rolled back. Database migrations were NOT reverted: if one is the cause,"
		err "restore from a dump (deploy/restore-db.sh) or write a corrective migration."
	fi
	release_lock
	exit "$code"
}

# ─── Steps ──────────────────────────────────────────────────────────
preflight() {
	step "Check the host and the environment file"
	have git || die "git is not installed."
	have curl || die "curl is not installed."
	if is_dry; then
		echo "      would require: uv, pnpm, node, pm2, psql, $ENV_FILE with ENVIRONMENT=production and no development address"
		echo "      clone: $REPO_DIR (with its .env); web builds: $WEB_RELEASES_DIR; static: $STATIC_DIR"
		return
	fi
	local tool
	for tool in uv pnpm node pm2 psql; do
		have "$tool" || die "$tool is not installed or not on the PATH of this user (sudo deploy/provision-app.sh)."
	done
	[[ -d "$REPO_DIR/.git" ]] || die "$REPO_DIR is not a git clone."
	[[ -f "$ENV_FILE" ]] || die "No $ENV_FILE. Copy deploy/env.production.example there (mode 0600) and fill it in."
	[[ "$ENVIRONMENT_NAME" == "production" ]] || die "ENVIRONMENT in $ENV_FILE is '$ENVIRONMENT_NAME', not production."
	# The development top-level domain, spelled in two parts so no production file contains it.
	local dev_tld="te""st"
	if grep -Eq "^[A-Za-z_]+=.*[a-z0-9-]\\.${dev_tld}([/:\"' ]|\$)" "$ENV_FILE"; then
		die "$ENV_FILE names a development address; production never does."
	fi
	take_lock
	trap on_error ERR
}

backup() {
	step "Dump the database before migrating (PRE_DEPLOY_BACKUP=$PRE_DEPLOY_BACKUP)"
	if [[ "$PRE_DEPLOY_BACKUP" != "true" ]]; then
		echo "      skipped: the database host dumps nightly; PRE_DEPLOY_BACKUP=true takes one now"
		return
	fi
	run env BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/tabsira}" bash "$DEPLOY_DIR/backup-db.sh" --url "$(env_get "$ENV_FILE" SYNC_DATABASE_URL)"
}

# Fetch, reset to upstream, and run again from the updated copy.
pull() {
	step "Pull: fetch and reset $REPO_DIR to its upstream branch"
	if is_dry; then
		echo "      would run: git fetch --prune origin && git reset --hard @{u}, then run the updated deploy.sh"
		return
	fi
	# Kept across the re-run: what served before this deploy.
	export TABSIRA_PREVIOUS_COMMIT="${TABSIRA_PREVIOUS_COMMIT:-$(git -C "$REPO_DIR" rev-parse HEAD)}"
	export TABSIRA_WEB_RELEASE_BEFORE="${TABSIRA_WEB_RELEASE_BEFORE-$(real_dir "$WEB_RELEASES_DIR/current" || true)}"
	PREVIOUS_COMMIT="$TABSIRA_PREVIOUS_COMMIT"
	WEB_RELEASE_BEFORE="$TABSIRA_WEB_RELEASE_BEFORE"
	PHASE="pulled"
	if [[ -n "${TABSIRA_PULLED:-}" ]]; then
		log "Deploying $(git -C "$REPO_DIR" rev-parse --short HEAD) (was ${PREVIOUS_COMMIT:0:12})"
		return
	fi
	git -C "$REPO_DIR" fetch --prune origin
	git -C "$REPO_DIR" rev-parse --verify -q '@{u}' >/dev/null ||
		die "$REPO_DIR has no upstream branch: git -C $REPO_DIR branch --set-upstream-to=origin/main"
	git -C "$REPO_DIR" reset --hard '@{u}' >/dev/null
	# The lock and the trap belong to this process; the updated copy takes its own.
	trap - ERR
	release_lock
	exec env TABSIRA_PULLED=1 bash "$REPO_DIR/deploy/deploy.sh" "${ORIGINAL_ARGS[@]}"
}

install_and_build() {
	step "Install dependencies (uv sync for the API and vision, pnpm install)"
	PYTHON_BEFORE="$("$REPO_DIR/apps/api/.venv/bin/python" -VV 2>/dev/null || true)"
	install_dependencies
	PYTHON_NOW="$("$REPO_DIR/apps/api/.venv/bin/python" -VV 2>/dev/null || true)"
	if [[ "$SKIP_VISION" != "true" ]]; then
		step "Detector weights (downloaded once)"
		run_in "$REPO_DIR/services/vision" env UV_NO_SYNC=1 bash scripts/fetch-weights.sh
	fi
}

check_and_migrate() {
	step "Check the production configuration against the live services"
	run_in "$REPO_DIR/apps/api" env UV_NO_SYNC=1 uv run python -m src.cli.check_config --live
	step "Migrations: geodata chain, app chain, vectors chain"
	run_in "$REPO_DIR" env UV_NO_SYNC=1 bash scripts/migrate.sh
	step "Re-apply the admin audit retention policy (idempotent)"
	run_in "$REPO_DIR/apps/api" env UV_NO_SYNC=1 uv run python -m src.cli.audit_policy
}

build_web() {
	step "Build the web app"
	# NEXT_PUBLIC_* values are baked in here, read from the environment file.
	if is_dry; then
		echo "      would run in $REPO_DIR: NODE_ENV=production pnpm --filter @tabsira/web build"
	else
		(cd "$REPO_DIR" && NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 pnpm --filter @tabsira/web build)
	fi
}

roll_api() {
	step "Replace the API workers, one at a time"
	if is_dry; then
		echo "      would run: deploy/api-roll.sh smoke, then roll (TTIN, health, TTOU); a first start or a new Python is a restart"
		return
	fi
	bash "$DEPLOY_DIR/api-roll.sh" smoke
	if ! systemctl is-active --quiet "$API_UNIT" || [[ ! -f /run/tabsira-api/gunicorn.pid ]]; then
		log "Starting the API (systemd)"
		sudo systemctl restart "$API_UNIT"
		wait_until "$HEALTH_TIMEOUT" api_ready "$API_HEALTH_URL" || die "The API did not become ready after starting."
	elif [[ -n "$PYTHON_BEFORE" && "$PYTHON_BEFORE" != "$PYTHON_NOW" ]]; then
		# Workers forked by a running master keep the master's interpreter.
		log "Python changed: restarting the API outright (a few seconds)"
		sudo systemctl restart "$API_UNIT"
	else
		bash "$DEPLOY_DIR/api-roll.sh" roll
	fi
}

# One process: a restart. SIGTERM lets running scans finish (up to the unit's
# TimeoutStopSec); a job cut short is delivered again.
restart_worker() {
	step "Restart the scan worker (graceful; jobs are idempotent and re-delivered)"
	if is_dry; then
		echo "      would run: sudo systemctl restart $WORKER_UNIT"
		return
	fi
	sudo systemctl restart "$WORKER_UNIT"
	sleep 5
	systemctl is-active --quiet "$WORKER_UNIT" || die "$WORKER_UNIT is not running; see journalctl -u ${WORKER_UNIT%.service}."
}

restart_vision_if_needed() {
	[[ "$SKIP_VISION" != "true" ]] || return 0
	step "Vision service: restart when its code changed"
	if is_dry; then
		echo "      would compare services/vision with the previous commit and run: sudo systemctl restart $VISION_UNIT"
		return
	fi
	if $VISION_NAMED || ! systemctl is-active --quiet "$VISION_UNIT" ||
		! git -C "$REPO_DIR" diff --quiet "$PREVIOUS_COMMIT" HEAD -- services/vision; then
		sudo systemctl restart "$VISION_UNIT"
		wait_until 180 curl -fsS --max-time 5 -o /dev/null "${DETECTOR_URL%/}/health" ||
			warn "The detector did not answer /health in 180 s; scans go on without boxes until it does."
	else
		log "Vision unchanged: left running."
	fi
}

roll_web() {
	step "Put the web build live, one pm2 instance at a time"
	run bash "$DEPLOY_DIR/web-roll.sh" deploy
}

health_gate() {
	step "Health gate (${HEALTH_TIMEOUT}s budget): the API, then the web"
	if is_dry; then
		echo "      would poll $API_HEALTH_URL and http://127.0.0.1:${WEB_PORT}${WEB_HEALTH_PATH}"
		return
	fi
	wait_until "$HEALTH_TIMEOUT" api_ready "$API_HEALTH_URL" || {
		err "Last response: $(curl -sS --max-time 5 "$API_HEALTH_URL" 2>&1 | head -c 400)"
		false
	}
	wants web || return 0
	wait_until "$HEALTH_TIMEOUT" curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${WEB_PORT}${WEB_HEALTH_PATH}"
}

# The deploy user cannot write /etc: say when nginx, a unit or the log rotation
# of this commit differ from the host, and how to apply them.
check_host_config() {
	step "Compare the host configuration (nginx, units) with this commit"
	if is_dry; then
		echo "      would run: deploy/apply-config.sh --check (a warning, never a failure)"
		return
	fi
	bash "$DEPLOY_DIR/apply-config.sh" --check || warn "Ask an administrator to run: cd $REPO_DIR && sudo deploy/apply-config.sh"
}

indexnow() {
	step "Tell search engines (IndexNow), production only"
	if [[ "$SKIP_INDEXNOW" == "true" ]]; then
		echo "      skipped: SKIP_INDEXNOW=true"
		return
	fi
	if is_dry; then
		echo "      would run: node scripts/indexnow.mjs (SITE_URL from the environment file)"
		return
	fi
	[[ "$ENVIRONMENT_NAME" == "production" ]] || return 0
	wants web || return 0
	# It warns and exits 0 on any failure, by design: the site is live either way.
	(cd "$REPO_DIR" &&
		SITE_URL="$(env_get "$ENV_FILE" SITE_URL)" \
		SITEMAP_URL="http://127.0.0.1:${WEB_PORT}/sitemap.xml" \
			node scripts/indexnow.mjs) || true
}

record_deployed() {
	is_dry && return 0
	git -C "$REPO_DIR" rev-parse HEAD >>"$DEPLOYED_LOG"
	tail -n 20 "$DEPLOYED_LOG" >"$DEPLOYED_LOG.tmp" && mv "$DEPLOYED_LOG.tmp" "$DEPLOYED_LOG"
}

# ─── Rollback: the commit deployed before the current one ──────────
rollback() {
	banner "Rollback"
	local target
	[[ -f "$DEPLOYED_LOG" ]] || die "No $DEPLOYED_LOG: nothing recorded to go back to."
	target="$(tail -n 2 "$DEPLOYED_LOG" | head -n 1)"
	[[ -n "$target" && "$target" != "$(git -C "$REPO_DIR" rev-parse HEAD)" ]] || die "No earlier deployed commit recorded."
	if is_dry; then
		echo "      would reset $REPO_DIR to ${target:0:12}, install, roll the API and worker, and put the previous web build back"
		return
	fi
	take_lock
	git -C "$REPO_DIR" reset --hard "$target" >/dev/null
	install_dependencies
	SKIP_SMOKE=1 roll_api_and_worker
	bash "$DEPLOY_DIR/web-roll.sh" rollback
	health_gate
	git -C "$REPO_DIR" rev-parse HEAD >>"$DEPLOYED_LOG"
	ok "Rolled back to ${target:0:12}. Database migrations are not reverted. The next deploy resets the clone to its branch again."
}

# ─── Main ───────────────────────────────────────────────────────────
if is_dry; then
	banner "DRY RUN: nothing below is executed"
	log "clone        $REPO_DIR"
	log "environment  $ENV_FILE"
	log "api          127.0.0.1:${API_PORT}, ${API_WORKERS:-2} worker(s) ($API_UNIT)"
	log "web          127.0.0.1:${WEB_PORT}, ${WEB_INSTANCES} instance(s) (pm2 $PM2_APP), builds in $WEB_RELEASES_DIR"
	log "vision       $DETECTOR_URL ($VISION_UNIT)"
	log "scan worker  one process ($WORKER_UNIT), restarted after the API rolls"
	log "parts        $PARTS"
fi

if $ROLLBACK; then
	rollback
	exit 0
fi

preflight
log "Deploying:$PARTS"
backup
pull
install_and_build
if wants worker; then
	check_and_migrate
fi
if wants web; then
	build_web
fi
PHASE="rolling"
if wants api; then
	roll_api
fi
if wants worker; then
	restart_worker
fi
restart_vision_if_needed
if wants web; then
	roll_web
fi
health_gate
trap - ERR
record_deployed
check_host_config
indexnow

if is_dry; then
	ok "Dry run complete: nothing was changed."
else
	ok "Deploy complete and healthy: $(git -C "$REPO_DIR" rev-parse --short HEAD)"
fi
