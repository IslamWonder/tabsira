#!/usr/bin/env bash
# Point git at the repository's own hooks (scripts/git-hooks), for this checkout
# and every worktree made from it. Runs on `pnpm install` through the root
# package.json `prepare` script and from `make install`, so nobody has to
# remember it. Idempotent, and a no-op outside a git checkout.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

if ! git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	exit 0
fi

if [[ "$(git -C "$SCRIPT_DIR" config --get core.hooksPath || true)" != "scripts/git-hooks" ]]; then
	git -C "$SCRIPT_DIR" config core.hooksPath scripts/git-hooks
	ok "Git hooks installed (core.hooksPath = scripts/git-hooks)"
fi
chmod +x "$SCRIPT_DIR"/git-hooks/* 2>/dev/null || true
