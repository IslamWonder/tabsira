#!/usr/bin/env bash
# Run the scan worker, the one process that takes scan jobs from the Redis queue.
#
# Usage: scripts/dev-worker.sh
#
# The same command runs in production as its own service; the API's workers
# never consume the queue. It reads REDIS_URL and the database from the root .env.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# lib.sh belongs to the tooling; without it, define just what this script uses.
if [[ -f "$SCRIPT_DIR/lib.sh" ]]; then
	# shellcheck source=lib.sh
	source "$SCRIPT_DIR/lib.sh"
fi
declare -F log >/dev/null || log() { printf '[tabsira] %s\n' "$*"; }
declare -F die >/dev/null || die() {
	printf '[err ] %s\n' "$*" >&2
	exit 1
}
declare -F have >/dev/null || have() { command -v "$1" >/dev/null 2>&1; }

unset VIRTUAL_ENV
have uv || die "uv is not installed. See https://docs.astral.sh/uv/"
cd "$REPO_ROOT/apps/api"

log "Scan worker on the Redis queue. Ctrl+C stops it after the running scans."
exec uv run python -m src.cli.scan_worker
