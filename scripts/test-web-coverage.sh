#!/usr/bin/env bash
# Web tests with the 100 % coverage threshold (part of make coverage).
#
# Thresholds (lines, branches, functions, statements) live in
# apps/web/vitest.config.mts; vitest fails the run below them. Reports land in
# apps/web/coverage/: text in the terminal, html/index.html, coverage-summary.json,
# lcov.info (SonarQube) and cobertura-coverage.xml (Jenkins).
#
# Usage: scripts/test-web-coverage.sh [vitest arguments...]
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_ROOT"

if [[ ! -f apps/web/package.json ]]; then
	skip "apps/web does not exist yet; no web coverage to measure"
	exit 0
fi
require_cmd pnpm "Run: make install"
[[ -d apps/web/node_modules ]] || die "web dependencies are missing. Run: make install"

banner "Web tests with coverage"
set +e
pnpm --filter @tabsira/web test:coverage "$@"
status=$?
set -e

summary="apps/web/coverage/coverage-summary.json"
if in_ci; then
	metrics="${WORKSPACE:-.}/.ci_metrics"
	mkdir -p "$metrics"
	lines=0
	if [[ -f "$summary" ]]; then
		lines="$(node -p "require('./$summary').total.lines.pct" 2>/dev/null || echo 0)"
	fi
	printf '{"stage":"web-tests","status":"%s","coverage":%s}\n' \
		"$([[ $status -eq 0 ]] && echo passed || echo failed)" "$lines" >"$metrics/web-tests.json"
	ok "CI metrics written to $metrics/web-tests.json"
fi

log "Coverage reports: apps/web/coverage/index.html, lcov.info, cobertura-coverage.xml"
[[ $status -eq 0 ]] || die "Web tests or the 100 % coverage gate failed (exit $status)."
ok "Web coverage complete."
