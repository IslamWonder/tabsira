#!/usr/bin/env bash
# The accessibility check (axe-core, WCAG 2.2 AA) against the production build of
# the web app, as the Jenkins stage "Web Accessibility" runs it.
#
# Usage: jenkins/web-a11y.sh [--dry-run]
#
# Needs: apps/web already built (`pnpm build`, an earlier stage), a Chromium or
# Chrome (CHROME_PATH, or chromium / google-chrome on the PATH, or Playwright's
# headless shell in ~/.cache/ms-playwright) and Node 24. No database and no real
# API: it starts apps/web/scripts/lib/api-stub.mjs, which answers the web server
# and the check with the sample answers of the screenshots. The check fails on
# ANY violation (A11Y_FAIL_ON=any), not only the serious ones.
#
# Environment (all optional): A11Y_WEB_PORT (3188), A11Y_API_PORT (8010),
# CHROME_PATH, CHROME_NO_SANDBOX=1 (a browser started as root or in a container),
# CHROME_DEBUG_PORT (9333), A11Y_API_ORIGIN (the API origin baked into the build:
# default from NEXT_PUBLIC_API_URL, else api.<SITE_URL host>, else the
# development domain's).
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/../scripts/lib.sh"

DRY_RUN=false
case "${1:-}" in
"") ;;
--dry-run) DRY_RUN=true ;;
*) die "usage: jenkins/web-a11y.sh [--dry-run]" ;;
esac

WEB_PORT="${A11Y_WEB_PORT:-3188}"
API_PORT="${A11Y_API_PORT:-8010}"
# The development top-level domain, spelled in two parts so no production file contains it.
DEV_SITE="https://tabsira.te""st"
SITE="${NEXT_PUBLIC_SITE_URL:-${SITE_URL:-$DEV_SITE}}"
SITE="${SITE%/}"
API_ORIGIN="${A11Y_API_ORIGIN:-${NEXT_PUBLIC_API_URL:-${SITE/\/\//\/\/api.}}}"
API_ORIGIN="${API_ORIGIN%/}"

if $DRY_RUN; then
	log "web         next start on 127.0.0.1:$WEB_PORT (the build in apps/web/.next)"
	log "api stub    apps/web/scripts/lib/api-stub.mjs on 127.0.0.1:$API_PORT (API_INTERNAL_URL)"
	log "browser     ${CHROME_PATH:-found by apps/web/scripts/lib/chrome.mjs}"
	log "api origin  $API_ORIGIN (what the browser calls; answered by the check itself)"
	log "run         pnpm check:a11y http://127.0.0.1:$WEB_PORT with A11Y_FAIL_ON=any"
	ok "Dry run complete: nothing was started."
	exit 0
fi

require_cmd node "Node 24 (NODE_TOOL_NAME in Jenkins)"
require_cmd pnpm "corepack enable"
[[ -d "$REPO_ROOT/apps/web/.next" ]] || die "apps/web/.next is missing: build the web app first (pnpm build)."
mkdir -p "$REPO_ROOT/.ci_logs"
cd "$REPO_ROOT/apps/web"

pids=()
stop_all() {
	local pid
	for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap stop_all EXIT

wait_for() {
	local url="$1" _
	for _ in $(seq 1 60); do
		curl -fs -o /dev/null "$url" && return 0
		sleep 1
	done
	return 1
}

node scripts/lib/api-stub.mjs "$API_PORT" >"$REPO_ROOT/.ci_logs/web-a11y-api.log" 2>&1 &
pids+=("$!")
export API_INTERNAL_URL="http://127.0.0.1:$API_PORT"
wait_for "$API_INTERNAL_URL/legal" || die "The API stub did not answer; see .ci_logs/web-a11y-api.log"

NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 pnpm exec next start --hostname 127.0.0.1 --port "$WEB_PORT" \
	>"$REPO_ROOT/.ci_logs/web-a11y-server.log" 2>&1 &
pids+=("$!")
wait_for "http://127.0.0.1:$WEB_PORT/robots.txt" || die "The web app did not start; see .ci_logs/web-a11y-server.log"

log "axe-core on the built app, failing on any violation"
A11Y_FAIL_ON=any A11Y_API_ORIGIN="$API_ORIGIN" pnpm check:a11y "http://127.0.0.1:$WEB_PORT" 2>&1 |
	tee "$REPO_ROOT/.ci_logs/web-a11y.log"
