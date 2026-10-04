#!/usr/bin/env bash
# Run the API, the scan worker, the web app and (when present) the vision service,
# behind https://tabsira.test (nginx and mkcert: scripts/setup-nginx-local.sh).
#
#   api     scripts/dev-api.sh             127.0.0.1:8000
#   worker  scripts/dev-worker.sh          the scan jobs, from Redis
#   web     pnpm dev in apps/web           127.0.0.1:3000
#   vision  scripts/dev-vision.sh          when that script exists
#
# Every line of output is prefixed with the service name. When one service
# stops, the others are stopped too, so a crash is never left half-running.
# Ctrl-C stops everything. A service whose app does not exist yet is skipped.
#
# Usage: scripts/dev.sh      (make dev)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

# Each background job gets its own process group, so a whole service (pnpm,
# next, node) can be stopped at once.
set -m

[[ -f .env ]] || warn ".env is missing: run bash scripts/setup-db.sh (or scripts/provision-dev.sh)"
if ! grep -qE '(^|[[:space:]])tabsira\.test([[:space:]]|$)' /etc/hosts 2>/dev/null; then
	warn "tabsira.test is not in /etc/hosts: run bash scripts/setup-nginx-local.sh"
fi

names=()
pids=()

prefix() {
	awk -v p="[$1]" '{ print p " " $0; fflush() }'
}

start() {
	local name="$1"
	shift
	log "starting $name"
	"$@" > >(prefix "$name") 2>&1 &
	names+=("$name")
	pids+=("$!")
}

stop_all() {
	local pid
	trap - INT TERM EXIT
	for pid in ${pids[@]+"${pids[@]}"}; do
		kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
	done
	wait 2>/dev/null || true
}
trap 'stop_all; exit 130' INT TERM
trap stop_all EXIT

if [[ -f apps/api/pyproject.toml && -f scripts/dev-api.sh ]]; then
	start api bash scripts/dev-api.sh
else
	skip "api: apps/api/pyproject.toml or scripts/dev-api.sh is missing"
fi

if [[ -f apps/api/pyproject.toml && -f scripts/dev-worker.sh ]]; then
	start worker bash scripts/dev-worker.sh
else
	skip "worker: apps/api/pyproject.toml or scripts/dev-worker.sh is missing"
fi

if [[ -f apps/web/package.json ]]; then
	require_cmd pnpm "Run: make install"
	start web env PORT="${WEB_PORT:-3000}" HOSTNAME=127.0.0.1 pnpm --dir apps/web run dev
else
	skip "web: apps/web does not exist yet"
fi

if [[ -f services/vision/pyproject.toml && -f scripts/dev-vision.sh ]]; then
	start vision bash scripts/dev-vision.sh
else
	skip "vision: services/vision or scripts/dev-vision.sh does not exist yet"
fi

[[ ${#pids[@]} -gt 0 ]] || die "nothing to run: no app exists yet"

log "running: ${names[*]}. Web https://tabsira.test, API https://api.tabsira.test. Ctrl-C stops all."
while :; do
	i=0
	for pid in "${pids[@]}"; do
		if ! kill -0 "$pid" 2>/dev/null; then
			err "${names[$i]} stopped; stopping the rest"
			exit 1
		fi
		i=$((i + 1))
	done
	sleep 1
done
