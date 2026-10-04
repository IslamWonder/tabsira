#!/usr/bin/env bash
# Helpers shared by the production delivery scripts in deploy/.
# Source it after the script's own `set -Eeuo pipefail`:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#
# Built on scripts/lib.sh (log, ok, warn, die, have, the user's own tools).
# These scripts run on the production hosts (Linux); the helpers here avoid
# GNU-only flags where that costs nothing, so --dry-run behaves the same on
# macOS and in Docker.
#
# Every path is configurable and none is a real host: the owners' hosts are
# supplied through the variables documented in deploy/env.production.example.

# shellcheck disable=SC1091
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)/../scripts/lib.sh"

DEPLOY_DIR="$REPO_ROOT/deploy"
export DEPLOY_DIR

# ─── Layout on the application host (as on the earlier prototype) ───
#   $REPO_DIR (/opt/tabsira)       the git clone: the API, the scan worker and vision run
#                                  from it, in place; deploys run from it and reset it
#   $REPO_DIR/.env                 the production environment file (0600, never in git)
#   $WEB_RELEASES_DIR/releases/<id>  (/srv/tabsira/web) each web build's own copy, so the
#                                  running Next.js never reads a build being replaced
#   $WEB_RELEASES_DIR/current      symlink to the live web build; previous: the one before
#   $STATIC_DIR (/srv/tabsira/static) every recent build's /_next/static, served by nginx
REPO_DIR="${REPO_DIR:-/opt/tabsira}"
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
WEB_RELEASES_DIR="${WEB_RELEASES_DIR:-/srv/tabsira/web}"
STATIC_DIR="${STATIC_DIR:-/srv/tabsira/static}"

API_UNIT="${API_UNIT:-tabsira-api.service}"
VISION_UNIT="${VISION_UNIT:-tabsira-vision.service}"
WORKER_UNIT="${WORKER_UNIT:-tabsira-worker.service}"
PM2_APP="${PM2_APP:-tabsira-web}"

# ─── Dry run ────────────────────────────────────────────────────────
# DRY_RUN=true prints what would run and runs nothing that changes a host.
DRY_RUN="${DRY_RUN:-false}"

set_dry_run() { DRY_RUN=true; }

is_dry() { [[ "$DRY_RUN" == "true" ]]; }

# step TITLE: a numbered heading, so a dry run reads as the plan.
STEP_NUMBER=0
step() {
	STEP_NUMBER=$((STEP_NUMBER + 1))
	log "[$STEP_NUMBER] $*"
}

# run CMD...: execute, or in a dry run print the command, shell-quoted.
run() {
	if is_dry; then
		printf '      would run:'
		printf ' %q' "$@"
		printf '\n'
	else
		"$@"
	fi
}

# run_in DIR CMD...: the same, from DIR.
run_in() {
	local dir="$1"
	shift
	if is_dry; then
		printf '      would run in %s:' "$dir"
		printf ' %q' "$@"
		printf '\n'
	else
		(cd "$dir" && "$@")
	fi
}

# ─── Small helpers ──────────────────────────────────────────────────

# KEY from an env file: the last assignment wins, quotes dropped. Prints
# nothing when the file or the key is missing. Never sources the file: a
# value may hold shell syntax (a JSON price list, a quoted sender).
env_get() {
	local file="$1" key="$2"
	[[ -f "$file" ]] || return 0
	{ grep -E "^${key}=" "$file" || true; } | tail -n 1 | cut -d= -f2- |
		sed -E "s/^\"(.*)\"\$/\\1/; s/^'(.*)'\$/\\1/"
}

# The physical path of a directory or of a symlink to one (readlink -f is GNU only).
real_dir() {
	(cd -P "$1" 2>/dev/null && pwd -P)
}

# The id (folder name) of the release a link points at; empty when it points at none.
release_id_of() {
	local real
	real="$(real_dir "$1" || true)"
	[[ -n "$real" ]] || return 0
	basename "$real"
}

# Point LINK at TARGET with one atomic rename, so a reader sees the old or the
# new release and never none. GNU mv takes -T, BSD mv takes -h.
atomic_link() {
	local target="$1" link="$2" tmp="$2.next.$$"
	ln -sfn "$target" "$tmp"
	if mv -Tf "$tmp" "$link" 2>/dev/null; then
		return 0
	fi
	mv -fh "$tmp" "$link"
}

# Readiness of the API: its JSON says "ok".
api_ready() {
	curl -fsS --max-time 5 "$1" 2>/dev/null | grep -q '"status":"ok"'
}

# Wait up to SECONDS for the command that follows to succeed.
wait_until() {
	local seconds="$1" deadline
	shift
	deadline=$((SECONDS + seconds))
	until "$@"; do
		((SECONDS < deadline)) || return 1
		sleep 1
	done
}

# The values the roll scripts and the deploy script agree on, read once from
# the environment file. A value set in the environment of the caller wins.
load_runtime_settings() {
	API_HOST="${API_HOST:-$(env_get "$ENV_FILE" API_HOST)}"
	API_HOST="${API_HOST:-127.0.0.1}"
	API_PORT="${API_PORT:-$(env_get "$ENV_FILE" API_PORT)}"
	API_PORT="${API_PORT:-8000}"
	API_WORKERS="${API_WORKERS:-$(env_get "$ENV_FILE" API_WORKERS)}"
	WEB_PORT="${WEB_PORT:-$(env_get "$ENV_FILE" WEB_PORT)}"
	WEB_PORT="${WEB_PORT:-3000}"
	WEB_INSTANCES="${WEB_INSTANCES:-$(env_get "$ENV_FILE" WEB_INSTANCES)}"
	WEB_INSTANCES="${WEB_INSTANCES:-2}"
	DETECTOR_URL="${DETECTOR_URL:-$(env_get "$ENV_FILE" DETECTOR_URL)}"
	DETECTOR_URL="${DETECTOR_URL:-http://127.0.0.1:8100}"
	export API_HOST API_PORT WEB_PORT WEB_INSTANCES
}
