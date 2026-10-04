#!/usr/bin/env bash
# Blocking security gate.
#
# scripts/audit.sh runs many advisory tools and tolerates findings. This script
# is the opposite: a short list of checks that must be clean for a build to be
# shippable. It runs all of them, then exits non-zero if any failed; CI must not
# swallow that exit code.
#
#   1. gitleaks   no secret in the working tree and none anywhere in the history
#                 (a secret deleted in a later commit is still a leaked secret)
#   2. pnpm audit no critical advisory in a production dependency
#
# Usage: scripts/security-gate.sh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

failures=0
failed_checks=""

gate() {
	local name="$1"
	shift
	banner "$name"
	if "$@"; then
		ok "$name passed"
	else
		err "$name FAILED: this blocks the build"
		failures=$((failures + 1))
		failed_checks="$failed_checks $name"
	fi
}

gitleaks_check() {
	local rc=0
	gitleaks dir . --config .gitleaks.toml --redact --exit-code 1 || rc=1
	# A shallow clone has no history to scan; a full one is what CI must provide.
	gitleaks git . --config .gitleaks.toml --redact --exit-code 1 || rc=1
	return $rc
}

if have gitleaks; then
	gate "gitleaks (working tree and full history)" gitleaks_check
else
	err "gitleaks is not installed. Run: bash scripts/install-quality-tools.sh gitleaks"
	failures=$((failures + 1))
	failed_checks="$failed_checks gitleaks"
fi

# --prod only: a critical advisory in a build-time devDependency does not ship.
if have pnpm; then
	gate "pnpm audit (production dependencies, critical)" pnpm audit --prod --audit-level critical
else
	err "pnpm is not installed. Run: make install"
	failures=$((failures + 1))
	failed_checks="$failed_checks pnpm-audit"
fi

if in_ci; then
	mkdir -p "${WORKSPACE:-.}/.ci_metrics"
	printf '{"stage":"security-gate","status":"%s","failures":%d}\n' \
		"$([[ $failures -eq 0 ]] && echo passed || echo failed)" "$failures" \
		>"${WORKSPACE:-.}/.ci_metrics/security-gate.json"
fi

if [[ $failures -gt 0 ]]; then
	die "Security gate failed with $failures blocking finding(s):${failed_checks}"
fi
ok "Security gate passed"
