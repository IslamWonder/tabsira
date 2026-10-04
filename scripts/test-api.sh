#!/usr/bin/env bash
# Run the API test suite.
#
# Usage: scripts/test-api.sh [--xdist] [--cov] [pytest arguments...]
#   --xdist   run in parallel, one database per worker (pytest -n auto)
#   --cov     also print a coverage report (use scripts/test-coverage.sh for the gates)
#
# Database tests need the tabsira_test database: scripts/setup-db.sh creates it
# and writes TEST_DATABASE_URL into the root .env.

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

# Convenience flags are ours; everything else goes to pytest as it is.
PYTEST_ARGS=()
for arg in "$@"; do
	case "$arg" in
	--xdist) PYTEST_ARGS+=("-n" "auto") ;;
	--cov) PYTEST_ARGS+=("--cov=src" "--cov-report=term-missing") ;;
	*) PYTEST_ARGS+=("$arg") ;;
	esac
done

log "Running the API tests..."
# ${arr[@]+...} keeps an empty array from failing under set -u on bash < 4.4.
uv run pytest ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
