#!/usr/bin/env bash
# Advisory audit: static analysis, dependency advisories and hygiene checks.
#
# Unlike scripts/security-gate.sh this is not what blocks a build; Jenkins runs
# it for the report and marks the build unstable on findings. It still exits
# non-zero when a step reports something, so the report cannot be mistaken for
# a clean run. A tool that is not installed, or an app that does not exist yet,
# is skipped with a notice.
#
# Python scanners run through uvx at a pinned version, so a linter never pins
# anything in the application's own dependencies.
#
# Usage: scripts/audit.sh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

SEMGREP_VERSION="1.179.0"
BANDIT_VERSION="1.9.4"

failures=0
skipped=0
failed_steps=""

# step NAME TOOL command...: run it when TOOL is installed.
step() {
	local name="$1" tool="$2"
	shift 2
	banner "$name"
	if ! have "$tool"; then
		skip "$tool is not installed (bash scripts/install-quality-tools.sh, or make install)"
		skipped=$((skipped + 1))
		return 0
	fi
	if "$@"; then
		ok "$name passed"
	else
		warn "$name reported findings"
		failures=$((failures + 1))
		failed_steps="$failed_steps
  - $name"
	fi
}

# Directories that exist now, from a list of candidates.
existing() {
	local dir
	for dir in "$@"; do
		[[ -d "$dir" ]] && printf '%s\n' "$dir"
	done
	return 0
}

python_targets=()
while IFS= read -r dir; do
	python_targets+=("$dir")
done < <(existing apps/api/src services/vision)

source_dirs=()
while IFS= read -r dir; do
	source_dirs+=("$dir")
done < <(existing apps/api/src apps/web/src services/vision packages)

shell_files=()
while IFS= read -r file; do
	shell_files+=("$file")
done < <(list_shell_files)

ruff_all() {
	local dir rc=0
	for dir in apps/api services/vision; do
		[[ -f "$dir/pyproject.toml" ]] || continue
		(cd "$dir" && uv run --quiet ruff check .) || rc=1
	done
	return $rc
}

lockfiles() {
	local file
	for file in pnpm-lock.yaml apps/api/uv.lock services/vision/uv.lock; do
		[[ -f "$file" ]] && printf -- '--lockfile=%s\n' "$file"
	done
	return 0
}

osv_all() {
	local args=()
	while IFS= read -r arg; do
		args+=("$arg")
	done < <(lockfiles)
	[[ ${#args[@]} -gt 0 ]] || {
		skip "no lock files yet"
		return 0
	}
	osv-scanner scan source "${args[@]}"
}

# 1. Semgrep: multi-language SAST (p/default needs the network)
if [[ ${#source_dirs[@]} -gt 0 ]]; then
	step "Semgrep (SAST)" uvx \
		uvx --from "semgrep==$SEMGREP_VERSION" semgrep --metrics=off --error \
		--config p/default --config .semgrep.yml "${source_dirs[@]}"
else
	banner "Semgrep (SAST)"
	skip "no source directories yet"
fi

# 2. Bandit: Python security
if [[ ${#python_targets[@]} -gt 0 ]]; then
	step "Bandit (Python security)" uvx \
		uvx --from "bandit==$BANDIT_VERSION" bandit -r "${python_targets[@]}" -c .bandit.yaml -q
else
	banner "Bandit (Python security)"
	skip "no Python sources yet"
fi

# 3. Ruff lint, 4. Biome lint
step "Ruff (Python lint)" uv ruff_all
step "Biome (TS/JS lint)" pnpm pnpm exec biome lint .

# 5. ShellCheck
if [[ ${#shell_files[@]} -gt 0 ]]; then
	step "ShellCheck (shell analysis)" shellcheck shellcheck "${shell_files[@]}"
fi

# 6. Secrets, 7. filesystem vulnerabilities, 8. locked dependencies
step "Gitleaks (secrets)" gitleaks gitleaks dir . --config .gitleaks.toml --redact --exit-code 1
step "Trivy (vulnerabilities, secrets, misconfiguration)" trivy trivy fs --config trivy.yaml --exit-code 1 .
step "OSV-Scanner (locked dependencies)" osv-scanner osv_all
step "pnpm audit (Node advisories, moderate and above)" pnpm pnpm audit --audit-level moderate

# 9. Hygiene
if [[ ${#source_dirs[@]} -gt 0 ]]; then
	step "jscpd (duplicated code)" pnpm pnpm exec jscpd --config .jscpd.json "${source_dirs[@]}"
fi
step "typos (spelling)" typos typos
step "markdownlint" pnpm pnpm exec markdownlint "**/*.md"

if in_ci; then
	mkdir -p "${WORKSPACE:-.}/.ci_metrics"
	printf '{"stage":"audit","status":"%s","failures":%d,"skipped":%d}\n' \
		"$([[ $failures -eq 0 ]] && echo passed || echo failed)" "$failures" "$skipped" \
		>"${WORKSPACE:-.}/.ci_metrics/audit.json"
fi

if [[ $failures -gt 0 ]]; then
	die "Audit: $failures step(s) reported findings:$failed_steps"
fi
ok "Audit finished: no findings ($skipped step(s) skipped)"
