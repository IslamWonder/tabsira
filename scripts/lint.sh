#!/usr/bin/env bash
# Format check, lint and type check for api, vision and web, plus the shell
# scripts. Every step runs even when an earlier one fails. An app that does not
# exist yet is skipped with a notice.
#
# Usage: scripts/lint.sh      (make lint)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

failed=""

check() {
	local name="$1"
	shift
	banner "$name"
	if "$@"; then
		ok "$name passed"
	else
		err "$name failed"
		failed="$failed
  - $name"
	fi
}

have pnpm || die "pnpm is not installed. Run: make install"
[[ -d node_modules ]] || die "node dependencies are missing. Run: make install"
have shellcheck || die "shellcheck is not installed. Run: bash scripts/install-quality-tools.sh shellcheck"

check "Format check" bash scripts/format.sh --check
# Biome: lint rules (noExplicitAny and the rest); formatting is the line above.
check "Biome lint (TS, JS, JSON)" pnpm exec biome lint .
check "Markdown lint" pnpm exec markdownlint "**/*.md"

shell_files=()
while IFS= read -r file; do
	shell_files+=("$file")
done < <(list_shell_files)
check "ShellCheck" shellcheck "${shell_files[@]}"

for dir in apps/api services/vision tools/mockdata; do
	if [[ -f "$dir/pyproject.toml" ]]; then
		require_cmd uv "Run: make install"
		check "Ruff lint ($dir)" bash -c "cd '$dir' && uv run --quiet ruff check ."
		# mypy takes its targets and strictness from [tool.mypy] in pyproject.toml.
		check "mypy ($dir)" bash -c "cd '$dir' && uv run --quiet mypy"
	else
		banner "Python lint: $dir"
		skip "$dir does not exist yet"
	fi
done

if [[ -f apps/web/package.json ]]; then
	check "Web lint and type check" pnpm turbo run lint type-check
else
	banner "Web lint and type check"
	skip "apps/web does not exist yet"
fi

if [[ -n "$failed" ]]; then
	die "Lint failed:$failed"
fi
ok "Lint passed"
