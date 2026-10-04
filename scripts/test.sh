#!/usr/bin/env bash
# Unit tests: api, vision and web. Every suite runs even when an earlier one
# fails, so one run shows everything that is broken. An app that does not exist
# yet is skipped with a notice. Unit tests never touch the network or a model;
# database tests use tabsira_test only.
#
# Usage: scripts/test.sh      (make test)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

ran=0
failed=""

suite() {
	local name="$1"
	shift
	banner "Tests: $name"
	ran=$((ran + 1))
	if "$@"; then
		ok "$name passed"
	else
		err "$name failed"
		failed="$failed $name"
	fi
}

# apps/api: its own script when the API engineer provides one.
if [[ -f apps/api/pyproject.toml ]]; then
	require_cmd uv "Run: make install"
	if [[ -f scripts/test-api.sh ]]; then
		suite "apps/api" bash scripts/test-api.sh
	else
		suite "apps/api" bash -c "cd apps/api && uv run pytest"
	fi
else
	banner "Tests: apps/api"
	skip "apps/api does not exist yet"
fi

if [[ -f services/vision/pyproject.toml ]]; then
	require_cmd uv "Run: make install"
	suite "services/vision" bash -c "cd services/vision && uv run pytest"
else
	banner "Tests: services/vision"
	skip "services/vision does not exist yet"
fi

if [[ -f apps/web/package.json ]]; then
	require_cmd pnpm "Run: make install"
	suite "apps/web" pnpm test
else
	banner "Tests: apps/web"
	skip "apps/web does not exist yet"
fi

if [[ $ran -eq 0 ]]; then
	warn "No test suite exists yet: nothing was run."
fi
if [[ -n "$failed" ]]; then
	die "Failed:$failed"
fi
ok "Tests passed ($ran suite(s))"
