#!/usr/bin/env bash
# Deploy TABSIRA to the production application host, as an atomic release.
# Each deploy is a releases/<id> folder and a `current` link, never an in-place
# `git reset`.
#
# Order, and why:
#   1. Lock, resolve the commit, check the host and the environment file.
#   2. Optionally dump the database first (PRE_DEPLOY_BACKUP=true).
#   3. Cut releases/<id> from the commit, install the API and vision with uv
#      and the workspace with pnpm, build the web app, assemble its standalone
#      build. The live release is never touched while this runs.
#   4. check_config --live, then the migrations: geodata chain, then app chain
#      (scripts/migrate.sh). A migration is not undone by a rollback; it must be
#      compatible with the release that is still serving while it runs.
#   5. Pre-flight: boot the new API and the new web build on spare ports.
#   6. Switch `current` (one atomic rename; `previous` keeps the old one).
#   7. Roll the API (gunicorn TTIN/TTOU), the web (pm2, one instance at a time)
#      and restart vision when its code changed. Each step is checked healthy.
#   8. Health gate; IndexNow last, production only; prune old releases.
#   On a failure after the switch: `current` goes back to the previous release
#   and the API and the web are rolled again. Nothing is rebuilt.
#
# Usage (on the application host, as the application user):
#   deploy/deploy.sh [--ref REF] [--dry-run]
#   deploy/deploy.sh --rollback [--dry-run]
#   --ref REF     commit, tag or branch to deploy (default: origin/main)
#   --dry-run     print every step with its values and run nothing
#   --rollback    switch to the previous release and roll again, no build
#
# Environment (all optional, see deploy/env.production.example):
#   APP_ROOT KEEP_RELEASES PRE_DEPLOY_BACKUP SKIP_VISION SKIP_INDEXNOW
#   WEB_HEALTH_PATH HEALTH_TIMEOUT and the paths of deploy/lib.sh.
# /etc/tabsira/deploy.env, when present, is read first.

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

REF="origin/main"
ROLLBACK=false
while [[ $# -gt 0 ]]; do
	case "$1" in
	--ref)
		[[ -n "${2:-}" ]] || die "--ref needs a value"
		REF="$2"
		shift 2
		;;
	--dry-run)
		DRY_RUN=true
		shift
		;;
	--rollback)
		ROLLBACK=true
		shift
		;;
	-h | --help)
		sed -n '2,/^set -Eeuo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
		exit 0
		;;
	*) die "Unknown option: $1 (see --help)" ;;
	esac
done

KEEP_RELEASES="${KEEP_RELEASES:-5}"
PRE_DEPLOY_BACKUP="${PRE_DEPLOY_BACKUP:-false}"
SKIP_VISION="${SKIP_VISION:-false}"
SKIP_INDEXNOW="${SKIP_INDEXNOW:-false}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
WEB_HEALTH_PATH="${WEB_HEALTH_PATH:-/}"
export WEB_HEALTH_PATH ENV_FILE APP_ROOT CURRENT_LINK STATIC_DIR DRY_RUN
LOCK_DIR="$SHARED_DIR/deploy.lock"

load_runtime_settings
API_HEALTH_URL="http://127.0.0.1:${API_PORT}/health/ready"
ENVIRONMENT_NAME="$(env_get "$ENV_FILE" ENVIRONMENT)"

PHASE="before-switch"
RELEASE=""
SHA=""
RELEASE_ID=""
PREVIOUS_REAL=""

# ─── Lock and failure handling ──────────────────────────────────────
release_lock() { rmdir "$LOCK_DIR" 2>/dev/null || true; }

# Roll the services onto whatever `current` points at now.
roll_services() {
	bash "$CURRENT_LINK/deploy/api-roll.sh" roll
	bash "$CURRENT_LINK/deploy/web-roll.sh" roll
}

on_error() {
	local code=$?
	trap - ERR
	err "Deploy failed (exit $code) in phase '$PHASE'."
	if [[ "$PHASE" == "switched" && -n "$PREVIOUS_REAL" && -d "$PREVIOUS_REAL" ]]; then
		err "Putting current back on $(basename "$PREVIOUS_REAL") and rolling the services again."
		atomic_link "$PREVIOUS_REAL" "$CURRENT_LINK"
		roll_services || err "The rollback roll failed too: check $API_UNIT and pm2 by hand."
		[[ -n "$RELEASE" ]] && : >"$RELEASE/.failed"
		err "Code rolled back. Database migrations were NOT reverted: if one is the cause,"
		err "restore from a dump (deploy/restore-db.sh) or write a corrective migration."
	elif [[ -n "$RELEASE" && -d "$RELEASE" ]]; then
		err "The live release was not touched. Removing the unfinished $RELEASE_ID."
		rm -rf "$RELEASE"
	fi
	release_lock
	exit "$code"
}

# ─── Rollback only ──────────────────────────────────────────────────
rollback_only() {
	local target current_real
	banner "Rollback"
	step "Switch current to the previous release"
	if is_dry; then
		echo "      would point $CURRENT_LINK at the release $PREVIOUS_LINK points to, and keep the old current as previous"
	else
		[[ -L "$PREVIOUS_LINK" ]] || die "No previous release recorded in $PREVIOUS_LINK."
		target="$(real_dir "$PREVIOUS_LINK")" || die "The previous release is gone."
		current_real="$(real_dir "$CURRENT_LINK" || true)"
		[[ -z "$current_real" ]] || atomic_link "$current_real" "$PREVIOUS_LINK"
		atomic_link "$target" "$CURRENT_LINK"
		log "current -> $(basename "$target")"
	fi
	step "Roll the API and the web onto it"
	if is_dry; then
		echo "      would run: $DEPLOY_DIR/api-roll.sh roll and web-roll.sh roll"
	else
		roll_services
	fi
	restart_vision_if_needed
	health_gate
	ok "Rolled back. Database migrations are not reverted."
}

# ─── Steps ──────────────────────────────────────────────────────────
preflight() {
	step "Check the host and the environment file"
	have git || die "git is not installed."
	have curl || die "curl is not installed."
	if is_dry; then
		echo "      would require: uv, pnpm, node, pm2, $ENV_FILE with ENVIRONMENT=production and no development address"
		echo "      layout: $APP_ROOT/{repo,releases,current,previous,shared,static}"
		return
	fi
	local tool
	for tool in uv pnpm node pm2 psql; do
		have "$tool" || die "$tool is not installed or not on the PATH of this user."
	done
	[[ -f "$ENV_FILE" ]] || die "No $ENV_FILE. Copy deploy/env.production.example there and fill it in."
	[[ "$ENVIRONMENT_NAME" == "production" ]] || die "ENVIRONMENT in $ENV_FILE is '$ENVIRONMENT_NAME', not production."
	# The development top-level domain, spelled in two parts so no production file contains it.
	local dev_tld="te""st"
	if grep -Eq "^[A-Za-z_]+=.*[a-z0-9-]\\.${dev_tld}([/:\"' ]|\$)" "$ENV_FILE"; then
		die "$ENV_FILE names a development address; production never does."
	fi
	# shellcheck disable=SC2153  # STATE_DIR is set in lib.sh
	mkdir -p "$RELEASES_DIR" "$STATE_DIR" "$CACHE_DIR/uv" "$CACHE_DIR/pnpm" "$STATIC_DIR"
	mkdir "$LOCK_DIR" 2>/dev/null || die "Another deploy holds $LOCK_DIR (remove it if none is running)."
	trap on_error ERR
	trap release_lock EXIT
}

resolve_ref() {
	step "Resolve the commit ($REF)"
	if is_dry; then
		SHA="$(git -C "$REPO_ROOT" rev-parse --verify "$REF^{commit}" 2>/dev/null || echo "0000000000000000000000000000000000000000")"
		echo "      would run: git -C $REPO_DIR fetch --prune origin"
	else
		git -C "$REPO_DIR" fetch --prune origin
		SHA="$(git -C "$REPO_DIR" rev-parse --verify "$REF^{commit}")"
	fi
	RELEASE_ID="$(date -u +%Y%m%d%H%M%S)-${SHA:0:12}"
	RELEASE="$RELEASES_DIR/$RELEASE_ID"
	log "Commit $SHA -> release $RELEASE_ID"
}

backup() {
	step "Dump the database before migrating (PRE_DEPLOY_BACKUP=$PRE_DEPLOY_BACKUP)"
	if [[ "$PRE_DEPLOY_BACKUP" != "true" ]]; then
		echo "      skipped: scheduled backups run on the data host; PRE_DEPLOY_BACKUP=true takes one now"
		return
	fi
	if is_dry; then
		echo "      would run: $DEPLOY_DIR/backup-db.sh --url \"\$SYNC_DATABASE_URL\""
		return
	fi
	bash "$DEPLOY_DIR/backup-db.sh" --url "$(env_get "$ENV_FILE" SYNC_DATABASE_URL)"
}

build_release() {
	step "Cut the release and install dependencies"
	run mkdir -p "$RELEASE"
	if is_dry; then
		echo "      would run: git -C $REPO_DIR archive $SHA | tar -x -C $RELEASE"
	else
		git -C "$REPO_DIR" archive "$SHA" | tar -x -C "$RELEASE"
		echo "$SHA" >"$RELEASE/REVISION"
		git -C "$REPO_DIR" rev-parse "$SHA:services/vision" >"$RELEASE/.vision-tree"
	fi
	run ln -s "$ENV_FILE" "$RELEASE/.env"

	# The Python that apps/api/.python-version names, as uv builds it, never the system one.
	export UV_PYTHON_PREFERENCE=only-managed UV_CACHE_DIR="$CACHE_DIR/uv" UV_LINK_MODE=hardlink
	run_in "$RELEASE/apps/api" uv sync --frozen --no-dev
	if [[ "$SKIP_VISION" != "true" ]]; then
		run_in "$RELEASE/services/vision" uv sync --frozen --no-dev
	fi
	run_in "$RELEASE" pnpm install --frozen-lockfile --store-dir "$CACHE_DIR/pnpm"

	step "Build the web app and assemble its standalone build"
	# NEXT_PUBLIC_* values are baked in here, read from the environment file
	# through the release's .env link; the build refuses a development address.
	if is_dry; then
		echo "      would run in $RELEASE: NODE_ENV=production pnpm --filter @tabsira/web build"
	else
		(cd "$RELEASE" && NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 pnpm --filter @tabsira/web build)
	fi
	run bash "$RELEASE/deploy/web-roll.sh" assemble "$RELEASE"
	# The running web needs only release/web; the sources' node_modules are dead weight.
	run rm -rf "$RELEASE/node_modules" "$RELEASE/apps/web/node_modules" "$RELEASE/apps/web/.next"
}

fetch_vision_weights() {
	[[ "$SKIP_VISION" != "true" ]] || return 0
	step "Detector weights (kept in the shared folder, downloaded once)"
	run_in "$RELEASE/services/vision" env UV_NO_SYNC=1 VISION_WEIGHTS_DIR="${VISION_WEIGHTS_DIR:-$SHARED_DIR/vision-weights}" bash scripts/fetch-weights.sh
}

check_and_migrate() {
	step "Check the production configuration against the live services"
	run_in "$RELEASE/apps/api" env UV_NO_SYNC=1 uv run python -m src.cli.check_config --live
	step "Migrations: geodata chain, then app chain"
	run_in "$RELEASE" env UV_NO_SYNC=1 bash scripts/migrate.sh
	step "Re-apply the admin audit retention policy (idempotent)"
	run_in "$RELEASE/apps/api" env UV_NO_SYNC=1 uv run python -m src.cli.audit_policy
}

preflight_boot() {
	step "Pre-flight: boot the new API and web build on spare ports"
	run bash "$RELEASE/deploy/api-roll.sh" smoke "$RELEASE"
	run bash "$RELEASE/deploy/web-roll.sh" smoke "$RELEASE"
}

switch_release() {
	step "Switch current to the new release"
	if is_dry; then
		echo "      would link previous -> the live release, then current -> $RELEASE_ID (atomic rename)"
		return
	fi
	PREVIOUS_REAL="$(real_dir "$CURRENT_LINK" || true)"
	[[ -z "$PREVIOUS_REAL" ]] || atomic_link "$PREVIOUS_REAL" "$PREVIOUS_LINK"
	atomic_link "$RELEASE" "$CURRENT_LINK"
	PHASE="switched"
	log "current -> $RELEASE_ID"
}

roll_api() {
	step "Roll the API workers, one at a time"
	if is_dry; then
		echo "      would run: $DEPLOY_DIR/api-roll.sh roll (TTIN, health, TTOU)"
		echo "      a first start, or a changed Python, is a systemctl restart $API_UNIT instead"
		return
	fi
	local python_now python_before
	python_now="$("$CURRENT_LINK/apps/api/.venv/bin/python" -VV 2>/dev/null || true)"
	python_before=""
	if [[ -n "$PREVIOUS_REAL" && -x "$PREVIOUS_REAL/apps/api/.venv/bin/python" ]]; then
		python_before="$("$PREVIOUS_REAL/apps/api/.venv/bin/python" -VV 2>/dev/null || true)"
	fi
	if ! systemctl is-active --quiet "$API_UNIT" || [[ ! -f /run/tabsira-api/gunicorn.pid ]]; then
		log "Starting the API (systemd)"
		sudo systemctl restart "$API_UNIT"
		wait_until "$HEALTH_TIMEOUT" api_ready "$API_HEALTH_URL" || die "The API did not become ready after starting."
	elif [[ -n "$python_before" && "$python_before" != "$python_now" ]]; then
		# Workers forked by a running master keep the master's interpreter.
		log "Python changed: restarting the API outright (a few seconds)"
		sudo systemctl restart "$API_UNIT"
	else
		bash "$CURRENT_LINK/deploy/api-roll.sh" roll
	fi
}

roll_web() {
	step "Roll the web instances, one at a time"
	run bash "$CURRENT_LINK/deploy/web-roll.sh" roll
}

restart_vision_if_needed() {
	[[ "$SKIP_VISION" != "true" ]] || return 0
	step "Vision service: restart when its code changed"
	if is_dry; then
		echo "      would compare services/vision between releases and run: sudo systemctl restart $VISION_UNIT"
		return
	fi
	local before="" now=""
	[[ -n "$PREVIOUS_REAL" && -f "$PREVIOUS_REAL/.vision-tree" ]] && before="$(cat "$PREVIOUS_REAL/.vision-tree")"
	[[ -f "$CURRENT_LINK/.vision-tree" ]] && now="$(cat "$CURRENT_LINK/.vision-tree")"
	if ! systemctl is-active --quiet "$VISION_UNIT" || [[ "$before" != "$now" ]]; then
		sudo systemctl restart "$VISION_UNIT"
		wait_until 180 curl -fsS --max-time 5 -o /dev/null "${DETECTOR_URL%/}/health" ||
			warn "The detector did not answer /health in 180 s; scans go on without boxes until it does."
	else
		log "Vision unchanged: left running."
	fi
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
	wait_until "$HEALTH_TIMEOUT" curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${WEB_PORT}${WEB_HEALTH_PATH}"
}

# The deploy user cannot write /etc: say when nginx, a unit or the log rotation
# of this release differ from the host, and how to apply them.
check_host_config() {
	step "Compare the host configuration (nginx, units) with this release"
	if is_dry; then
		echo "      would run: $DEPLOY_DIR/apply-config.sh --check (a warning, never a failure)"
		return
	fi
	bash "$CURRENT_LINK/deploy/apply-config.sh" --check || warn "Ask an administrator to run: sudo $CURRENT_LINK/deploy/apply-config.sh"
}

indexnow() {
	step "Tell search engines (IndexNow), production only"
	if [[ "$SKIP_INDEXNOW" == "true" ]]; then
		echo "      skipped: SKIP_INDEXNOW=true"
		return
	fi
	if is_dry; then
		echo "      would run in the release: node scripts/indexnow.mjs (SITE_URL from the environment file; refuses anything but https://tabsira.me)"
		return
	fi
	[[ "$ENVIRONMENT_NAME" == "production" ]] || return 0
	# It warns and exits 0 on any failure, by design: the site is live either way.
	(cd "$RELEASE" &&
		SITE_URL="$(env_get "$ENV_FILE" SITE_URL)" \
		SITEMAP_URL="http://127.0.0.1:${WEB_PORT}/sitemap.xml" \
		INDEXNOW_STATE="$STATE_DIR/indexnow.json" \
			node scripts/indexnow.mjs) || true
}

# Keep KEEP_RELEASES, never current, previous or the release the API master
# was started from: its lazily imported modules still live there.
prune() {
	step "Prune old releases (keep $KEEP_RELEASES) and unreferenced static files"
	if is_dry; then
		echo "      would remove releases beyond the newest $KEEP_RELEASES, and static files older than WEB_STATIC_DAYS"
		return
	fi
	local keep_current keep_previous keep_master="" master old
	keep_current="$(real_dir "$CURRENT_LINK" || true)"
	keep_previous="$(real_dir "$PREVIOUS_LINK" || true)"
	if [[ -f /run/tabsira-api/gunicorn.pid ]]; then
		master="$(cat /run/tabsira-api/gunicorn.pid)"
		keep_master="$(readlink "/proc/$master/cwd" 2>/dev/null | sed -E 's#(/releases/[^/]+)/.*#\1#' || true)"
	fi
	# Newest first (the id starts with a UTC timestamp).
	for old in $(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +"$((KEEP_RELEASES + 1))"); do
		[[ "$old" == "$keep_current" || "$old" == "$keep_previous" || "$old" == "$keep_master" ]] && continue
		rm -rf "$old"
	done
	bash "$CURRENT_LINK/deploy/web-roll.sh" prune
	if [[ -n "$keep_master" && "$keep_master" != "$keep_current" && "$keep_master" != "$keep_previous" ]]; then
		warn "The API master still runs from $(basename "$keep_master"); restart it in a quiet hour: sudo systemctl restart $API_UNIT"
	fi
}

# ─── Main ───────────────────────────────────────────────────────────
if is_dry; then
	banner "DRY RUN: nothing below is executed"
	log "app root     $APP_ROOT"
	log "environment  $ENV_FILE"
	log "api          127.0.0.1:${API_PORT}, ${API_WORKERS:-2} worker(s) ($API_UNIT)"
	log "web          127.0.0.1:${WEB_PORT}, ${WEB_INSTANCES} instance(s) (pm2 $PM2_APP)"
	log "vision       $DETECTOR_URL ($VISION_UNIT)"
fi

if $ROLLBACK; then
	if ! is_dry; then
		mkdir -p "$STATE_DIR"
		mkdir "$LOCK_DIR" 2>/dev/null || die "Another deploy holds $LOCK_DIR."
		trap release_lock EXIT
	fi
	rollback_only
	exit 0
fi

preflight
resolve_ref
backup
build_release
fetch_vision_weights
check_and_migrate
preflight_boot
switch_release
roll_api
roll_web
restart_vision_if_needed
health_gate
trap - ERR
check_host_config
indexnow
prune

if is_dry; then
	ok "Dry run complete: nothing was changed."
else
	ok "Deploy complete and healthy: $RELEASE_ID"
fi
