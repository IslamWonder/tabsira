#!/usr/bin/env bash
# Install every dependency: web (pnpm workspace), api and vision (uv), git hooks.
# Apps that do not exist yet are skipped. In CI the lock files are authoritative:
# an out-of-date one fails the install instead of being rewritten.
#
# Usage: scripts/install.sh      (make install)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"
cd "$REPO_ROOT"

banner "Prerequisites"
have node || die "Node 24 is required (see .nvmrc). Install it with nvm, fnm or your package manager."
[[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 24 ]] ||
	die "Node 24 or newer is required, found $(node --version) (see .nvmrc)."
have uv || die "uv is required: https://docs.astral.sh/uv/getting-started/installation/"
ensure_pnpm_version
have pnpm || die "pnpm is required: npm install -g pnpm (the version is pinned in package.json)"
ok "node $(node --version), pnpm $(pnpm --version), $(uv --version)"

banner "Node workspace (pnpm)"
if in_ci; then
	pnpm install --frozen-lockfile
else
	pnpm install
fi

for dir in apps/api services/vision; do
	banner "Python: $dir (uv)"
	if [[ ! -f "$dir/pyproject.toml" ]]; then
		skip "$dir does not exist yet"
		continue
	fi
	if in_ci; then
		(cd "$dir" && uv sync --locked)
	else
		(cd "$dir" && uv sync)
	fi
done

banner "Git hooks"
bash "$SCRIPT_DIR/install-git-hooks.sh"
ok "Dependencies installed"
