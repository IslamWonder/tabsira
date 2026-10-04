#!/usr/bin/env bash
# Format the repository, or with --check only verify it (make format / make lint).
#
#   Python      ruff format          apps/api, services/vision (when present)
#   TS, JS, JSON  biome (format + import order, no lint rules)
#   Markdown    prettier             Biome does not format Markdown
#   Shell       shfmt                scripts/, jenkins/, docker/
#
# docs/spec and data/ are never touched: see biome.json and .prettierignore.
#
# Usage: scripts/format.sh [--check]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

CHECK=false
case "${1:-}" in
"") ;;
--check) CHECK=true ;;
*) die "usage: scripts/format.sh [--check]" ;;
esac

failures=0
failed_tools=""

fail() {
	err "$1"
	failures=$((failures + 1))
	failed_tools="$failed_tools $2"
}

# run LABEL TOOL command...: run a formatter; its success is the check's success.
run() {
	local label="$1" tool="$2"
	shift 2
	if "$@"; then
		ok "$label is clean"
	else
		if $CHECK; then
			fail "$label is not formatted" "$tool"
		else
			fail "$label could not be formatted" "$tool"
		fi
	fi
}

# ─── Python ─────────────────────────────────────────────────────────
banner "Python: ruff format"
for dir in apps/api services/vision; do
	if [[ ! -f "$dir/pyproject.toml" ]]; then
		skip "$dir does not exist yet"
		continue
	fi
	have uv || die "uv is not installed. Run: make install"
	if $CHECK; then
		run "$dir" ruff bash -c "cd '$dir' && uv run --quiet ruff format --check ."
	else
		run "$dir" ruff bash -c "cd '$dir' && uv run --quiet ruff format ."
	fi
done

# ─── Node tools ─────────────────────────────────────────────────────
have pnpm || die "pnpm is not installed. Run: make install"
[[ -d node_modules ]] || die "node dependencies are missing. Run: make install"

banner "TypeScript, JavaScript and JSON: biome"
if $CHECK; then
	run "TS/JS/JSON" biome pnpm exec biome check --linter-enabled=false .
else
	run "TS/JS/JSON" biome pnpm exec biome check --write --linter-enabled=false .
fi

banner "Markdown: prettier"
if $CHECK; then
	run "Markdown" prettier pnpm exec prettier --check "**/*.md"
else
	run "Markdown" prettier pnpm exec prettier --write "**/*.md"
fi

# ─── Shell ──────────────────────────────────────────────────────────
banner "Shell: shfmt"
if ! have shfmt; then
	die "shfmt is not installed. Run: bash scripts/install-quality-tools.sh shfmt"
fi
shell_files=()
while IFS= read -r file; do
	shell_files+=("$file")
done < <(list_shell_files)
if [[ ${#shell_files[@]} -eq 0 ]]; then
	skip "no shell scripts found"
elif $CHECK; then
	run "Shell" shfmt shfmt -d "${shell_files[@]}"
else
	run "Shell" shfmt shfmt -w "${shell_files[@]}"
fi

# ─── Result ─────────────────────────────────────────────────────────
if in_ci; then
	mkdir -p "${WORKSPACE:-.}/.ci_metrics"
	printf '{"stage":"format","status":"%s","failures":%d}\n' \
		"$([[ $failures -eq 0 ]] && echo passed || echo failed)" "$failures" \
		>"${WORKSPACE:-.}/.ci_metrics/format.json"
fi

if [[ $failures -gt 0 ]]; then
	if $CHECK; then
		die "Format check failed (${failed_tools# }). Run: make format"
	fi
	die "Formatting failed (${failed_tools# })"
fi

if $CHECK; then
	ok "All files are formatted"
else
	ok "All files formatted"
fi
