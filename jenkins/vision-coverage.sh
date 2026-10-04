#!/usr/bin/env bash
# Run the vision service's tests with coverage and write the reports the
# pipeline publishes and SonarQube reads.
#
# Usage: jenkins/vision-coverage.sh [pytest arguments...]
#
# Reports in services/vision/coverage/: coverage.xml (Cobertura), junit.xml and
# html/index.html. The 100 % gate is fail_under in services/vision/pyproject.toml,
# so no flag is needed here for it. Nothing here touches the network or a model:
# the tests fake Ultralytics.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/../scripts/lib.sh"

require_cmd uv "See https://docs.astral.sh/uv/"
cd "$REPO_ROOT/services/vision"

log "Running the vision tests with coverage..."
rm -rf coverage

set +e
uv run pytest --cov \
	--cov-report=term-missing \
	--cov-report=xml:coverage/coverage.xml \
	--cov-report=html:coverage/html \
	--junitxml=coverage/junit.xml \
	-o junit_family=xunit2 \
	"$@"
pytest_exit=$?
set -e

if in_ci; then
	metrics_dir="${WORKSPACE:-$REPO_ROOT}/.ci_metrics"
	mkdir -p "$metrics_dir"
	total=0 failures=0 errors=0 skipped=0 coverage=0
	if [[ -f coverage/junit.xml ]]; then
		total="$(grep -oE 'tests="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)"
		failures="$(grep -oE 'failures="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)"
		errors="$(grep -oE 'errors="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)"
		skipped="$(grep -oE 'skipped="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)"
	fi
	if [[ -f coverage/coverage.xml ]]; then
		line_rate="$(grep -oE 'line-rate="[0-9.]+"' coverage/coverage.xml | head -1 | grep -oE '[0-9.]+' || echo 0)"
		coverage="$(awk -v rate="$line_rate" 'BEGIN { printf "%.2f", rate * 100 }')"
	fi
	failed=$((failures + errors))
	passed=$((total - failed - skipped))
	[[ $passed -lt 0 ]] && passed=0
	printf '{"stage":"vision_tests","status":"%s","passed":%d,"failed":%d,"skipped":%d,"total":%d,"coverage":%s}\n' \
		"$([[ $pytest_exit -eq 0 ]] && echo passed || echo failed)" "$passed" "$failed" "$skipped" "$total" "$coverage" \
		>"$metrics_dir/vision_tests.json"
fi

log "Reports: services/vision/coverage/coverage.xml, junit.xml, html/index.html"
[[ $pytest_exit -eq 0 ]] || die "The vision tests or the coverage gate failed (exit $pytest_exit)."
ok "Vision coverage complete."
