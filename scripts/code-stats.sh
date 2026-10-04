#!/usr/bin/env bash
# A few lines about the code base: size, tests, schema, docs, coverage, today.
#
# Counts non-blank lines of the files git tracks, leaving out generated files
# (the OpenAPI types, lock files). Coverage comes from the reports the last
# `make coverage` left behind, with their age; nothing is run here, so it takes
# under a second. For depth (complexity, duplication) use `make audit`.
#
# Usage: scripts/code-stats.sh      (make stats)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

# Generated files are not counted. Filtered with grep rather than `:!` pathspecs:
# git 2.43 returns nothing at all when an exclude pathspec matches no file.
GENERATED='^apps/web/src/lib/api/(schema\.d\.ts|openapi\.json)$|(^|/)(uv\.lock|pnpm-lock\.yaml)$'
TESTS='\.test\.(ts|tsx|mjs)$|^apps/web/src/test/|^services/vision/tests/'

# Tracked files matching the pathspecs, generated files left out.
tracked() {
	git ls-files -- "$@" | grep -vE "$GENERATED" || true
}

# Of the file names on stdin, keep (keep) or drop (drop) the test files.
only_tests() { grep -E "$TESTS" || true; }
no_tests() { grep -vE "$TESTS" || true; }

# Non-blank lines of the files named on stdin.
lines() {
	tr '\n' '\0' | xargs -0 cat 2>/dev/null | awk 'NF { n++ } END { print n + 0 }'
}

# Lines of the files named on stdin that match the pattern.
matches() {
	tr '\n' '\0' | xargs -0 cat 2>/dev/null | awk -v p="$1" '$0 ~ p { n++ } END { print n + 0 }'
}

count() { awk 'END { print NR }'; }

# 12345 -> 12,345
n() {
	awk -v v="$1" 'BEGIN { s = sprintf("%d", v); while (s ~ /[0-9][0-9][0-9][0-9]/) sub(/[0-9][0-9][0-9]($|,)/, ",&", s); print s }'
}

# Whole minutes since a file changed, on Linux and macOS.
age_minutes() {
	local changed
	changed="$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1")"
	echo $((($(date +%s) - changed) / 60))
}

age() {
	local minutes
	minutes="$(age_minutes "$1")"
	if ((minutes < 60)); then echo "${minutes} min ago"; else echo "$((minutes / 60)) h ago"; fi
}

api_src=$(tracked 'apps/api/src/*.py' | lines)
api_tests=$(tracked 'apps/api/tests/*.py' | lines)
api_cases=$(tracked 'apps/api/tests/*.py' | matches '^[ \t]*(async )?def test_')
web_src=$(tracked 'apps/web/src/*.ts' 'apps/web/src/*.tsx' 'apps/web/src/*.css' | no_tests | lines)
web_tests=$(tracked 'apps/web/src/*.ts' 'apps/web/src/*.tsx' | only_tests | lines)
web_cases=$(tracked 'apps/web/src/*.ts' 'apps/web/src/*.tsx' | only_tests | matches '(^|[^A-Za-z_.])(it|test)(\.each\(.*\))?\(')
vision=$(tracked 'services/vision/*.py' | no_tests | lines)
ops=$(tracked 'scripts/*' 'deploy/*' 'jenkins/*' 'nginx/*' 'Jenkinsfile' 'Makefile' | no_tests | lines)
app_migrations=$(tracked 'apps/api/alembic/versions/*.py' | count)
geo_migrations=$(tracked 'apps/api/alembic_geodata/versions/*.py' | count)
tables=$(tracked 'apps/api/src/models/*.py' | matches '__tablename__ *=')
doc_files=$(tracked '*.md' | count)
doc_lines=$(tracked '*.md' | lines)
code_total=$((api_src + web_src + vision + ops))
test_total=$((api_tests + web_tests))

coverage="api –"
xml=apps/api/coverage/coverage.xml
if [[ -f "$xml" ]]; then
	coverage="api $(awk -F'line-rate="' 'NF > 1 { split($2, a, "\""); printf "%.1f %%", a[1] * 100; exit }' "$xml") ($(age "$xml"))"
fi
summary=apps/web/coverage/coverage-summary.json
if [[ -f "$summary" ]]; then
	coverage="$coverage · web $(awk -F'"pct":' 'NF > 1 { split($2, a, /[,}]/); printf "%.1f %%", a[1]; exit }' "$summary") ($(age "$summary"))"
else
	coverage="$coverage · web –"
fi

today=$(git log --since=midnight --pretty=format:%H | awk 'END { print NR }')
authors=$(git log --since=midnight --pretty=format:%an | sort -u | awk 'END { print NR }')
churn=$(git log --since=midnight --numstat --pretty=format: |
	awk -v g="$GENERATED" '$1 ~ /^[0-9]+$/ && $3 !~ g { a += $1; d += $2 } END { print a + 0, d + 0 }')

printf 'TABSIRA   %s@%s · %s commits · %s\n' "$(git rev-parse --abbrev-ref HEAD)" "$(git rev-parse --short HEAD)" \
	"$(n "$(git rev-list --count HEAD)")" "$(date -u '+%Y-%m-%d %H:%M UTC')"
printf 'Code      %s lines: api %s · web %s · vision %s · ops %s\n' "$(n "$code_total")" "$(n "$api_src")" "$(n "$web_src")" "$(n "$vision")" "$(n "$ops")"
printf 'Tests     %s lines · %s written (api %s, web %s) · %s test lines per code line\n' "$(n "$test_total")" \
	"$(n "$((api_cases + web_cases))")" "$(n "$api_cases")" "$(n "$web_cases")" \
	"$(awk -v t="$test_total" -v c="$((api_src + web_src))" 'BEGIN { printf "%.1f", (c ? t / c : 0) }')"
printf 'Schema    %s tables · %s app + %s geodata migrations\n' "$tables" "$app_migrations" "$geo_migrations"
printf 'Docs      %s files, %s lines\n' "$doc_files" "$(n "$doc_lines")"
printf 'Coverage  %s\n' "$coverage"
read -r added removed <<<"$churn"
printf 'Today     %s commits by %s author(s), +%s −%s lines\n' "$(n "$today")" "$authors" "$(n "$added")" "$(n "$removed")"
