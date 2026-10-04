#!/usr/bin/env bash
# Run the API tests with coverage and hold the code to the 100 % gates.
#
# Usage: scripts/test-coverage.sh [pytest arguments...]
#
# Two gates: the whole suite (fail_under = 100 in apps/api/pyproject.toml, with
# branch coverage) and the lines this change touches (diff-cover against main).
# Reports: apps/api/coverage/coverage.xml, junit.xml and html/index.html.
# PYTEST_WORKERS=N runs N workers, each with its own database.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# lib.sh belongs to the tooling; without it, define just what this script uses.
if [[ -f "$SCRIPT_DIR/lib.sh" ]]; then
	# shellcheck source=lib.sh
	source "$SCRIPT_DIR/lib.sh"
fi
declare -F log >/dev/null || log() { printf '[tabsira] %s\n' "$*"; }
declare -F ok >/dev/null || ok() { printf '[ ok ] %s\n' "$*"; }
declare -F warn >/dev/null || warn() { printf '[warn] %s\n' "$*" >&2; }
declare -F die >/dev/null || die() {
	printf '[err ] %s\n' "$*" >&2
	exit 1
}
declare -F have >/dev/null || have() { command -v "$1" >/dev/null 2>&1; }
declare -F in_ci >/dev/null || in_ci() { [[ "${CI:-}" == "true" || "${CI:-}" == "1" || "${JENKINS_BUILD:-}" == "true" || "${JENKINS_BUILD:-}" == "1" ]]; }

unset VIRTUAL_ENV
have uv || die "uv is not installed. See https://docs.astral.sh/uv/"
cd "$REPO_ROOT/apps/api"

log "Running the API tests with coverage..."

PYTEST_LOG="${WORKSPACE:-.}/.ci_logs/tests.log"
mkdir -p "$(dirname "$PYTEST_LOG")"

# Flush output at once so a CI monitor sees progress.
export PYTHONUNBUFFERED=1

# In CI, name every test and the slowest ones, so a hang is easy to find.
PYTEST_CI_ARGS=()
if in_ci; then
	PYTEST_CI_ARGS=("-v" "--durations=20")
fi

# Parallel runs are off by default: each worker builds or copies its own
# database, which only pays off once the suite is large enough. Turn it on with
# PYTEST_WORKERS after measuring on the machine in question.
PYTEST_PARALLEL_ARGS=()
if [[ "${PYTEST_WORKERS:-0}" != "0" ]]; then
	log "Running with ${PYTEST_WORKERS} workers, one database each"
	# loadfile keeps a module's tests on one worker.
	PYTEST_PARALLEL_ARGS=("-n" "${PYTEST_WORKERS}" "--dist" "loadfile")
fi

set +e
uv run pytest --cov=src --cov-report=term-missing \
	--cov-report=html:coverage/html \
	--cov-report=xml:coverage/coverage.xml \
	--junitxml=coverage/junit.xml \
	-o junit_family=xunit2 \
	${PYTEST_CI_ARGS[@]+"${PYTEST_CI_ARGS[@]}"} \
	${PYTEST_PARALLEL_ARGS[@]+"${PYTEST_PARALLEL_ARGS[@]}"} \
	"$@" 2>&1 | tee "$PYTEST_LOG"
PYTEST_EXIT=${PIPESTATUS[0]}
set -e

# ── Diff coverage: the lines this change touches must be covered ────
#
# Compared against main. On main itself `main..HEAD` is empty by definition, so
# the commit that just landed is measured instead; otherwise the rule would
# only ever apply to branches. A missing base is a checkout problem, reported
# as one rather than as a coverage failure.
current_branch() {
	# BRANCH_NAME is set by Jenkins multibranch jobs, whose checkout is detached.
	echo "${BRANCH_NAME:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)}"
}

resolve_compare_branch() {
	local candidate
	for candidate in origin/main main; do
		if git rev-parse --verify --quiet "$candidate" >/dev/null; then
			echo "$candidate"
			return 0
		fi
	done
	return 1
}

if [[ $PYTEST_EXIT -eq 0 && -f coverage/coverage.xml ]]; then
	COMPARE_BRANCH=""
	if [[ "$(current_branch)" == "main" ]]; then
		if git rev-parse --verify --quiet HEAD~1 >/dev/null; then
			log "On main: measuring the commit that just landed."
			COMPARE_BRANCH="HEAD~1"
		else
			log "On main with no parent commit; nothing to compare."
		fi
	elif ! COMPARE_BRANCH="$(resolve_compare_branch)"; then
		warn "Neither origin/main nor main exists; skipping diff coverage."
		warn "This is a checkout problem, not a coverage one."
		COMPARE_BRANCH=""
	fi

	if [[ -n "$COMPARE_BRANCH" ]]; then
		log "Checking diff coverage against ${COMPARE_BRANCH}..."
		if uv run diff-cover coverage/coverage.xml \
			--compare-branch="$COMPARE_BRANCH" \
			--fail-under=100 \
			--diff-range-notation=.. 2>&1 | tee -a "$PYTEST_LOG"; then
			ok "The changed lines meet the 100% coverage requirement."
		else
			die "The changed lines do not meet 100% coverage (see the report above)."
		fi
	fi
fi

# ── CI metrics ──────────────────────────────────────────────────────
if in_ci; then
	METRICS_DIR="${WORKSPACE:-.}/.ci_metrics"
	mkdir -p "$METRICS_DIR"

	TOTAL=0
	FAILURES=0
	ERRORS=0
	SKIPPED=0
	TIME="0"
	if [[ -f coverage/junit.xml ]]; then
		TOTAL=$(grep -oE 'tests="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)
		FAILURES=$(grep -oE 'failures="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)
		ERRORS=$(grep -oE 'errors="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)
		SKIPPED=$(grep -oE 'skipped="[0-9]+"' coverage/junit.xml | head -1 | grep -oE '[0-9]+' || echo 0)
		TIME=$(grep -oE 'time="[0-9.]+"' coverage/junit.xml | head -1 | grep -oE '[0-9.]+' | tr -d '\n\r' || echo 0)
	fi

	COVERAGE=0
	if [[ -f coverage/coverage.xml ]]; then
		LINE_RATE=$(grep -oE 'line-rate="[0-9.]+"' coverage/coverage.xml | head -1 | grep -oE '[0-9.]+' || echo 0)
		COVERAGE=$(awk "BEGIN {printf \"%.2f\", $LINE_RATE * 100}")
	fi

	FAILED=$((FAILURES + ERRORS))
	PASSED=$((TOTAL - FAILED - SKIPPED))
	[[ $PASSED -lt 0 ]] && PASSED=0
	STATUS="failed"
	[[ $PYTEST_EXIT -eq 0 ]] && STATUS="passed"

	printf '{"stage":"tests","status":"%s","passed":%d,"failed":%d,"skipped":%d,"total":%d,"duration":"%s","coverage":%s}\n' \
		"$STATUS" "$PASSED" "$FAILED" "$SKIPPED" "$TOTAL" "$TIME" "$COVERAGE" \
		>"$METRICS_DIR/tests.json"
	ok "CI metrics written to $METRICS_DIR/tests.json"
fi

log "Coverage reports:"
log "  - terminal: above"
log "  - HTML: apps/api/coverage/html/index.html"
log "  - XML:  apps/api/coverage/coverage.xml"

[[ $PYTEST_EXIT -eq 0 ]] || die "Tests or the coverage gate failed (exit $PYTEST_EXIT)."
ok "Test coverage complete."
