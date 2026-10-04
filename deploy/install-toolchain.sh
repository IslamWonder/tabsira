#!/usr/bin/env bash
# Install the build and run toolchain of the application user: nvm, the Node of
# .nvmrc, pnpm (the version package.json pins), pm2, uv and the Python of
# apps/api/.python-version as uv builds it. Everything lives in the user's home,
# so a deploy needs no root and the system Python and Node are never touched.
#
# Run as the application user (deploy/provision-app.sh does that), from a checkout:
#   deploy/install-toolchain.sh [--check]
#   --check   print what is installed and what would be, install nothing
#
# Idempotent. For the user's own shell, ~/.bashrc and ~/.zshrc (those that exist) get
# one marked section that loads nvm and puts ~/.local/bin on the PATH, replaced, never
# duplicated, on a re-run; TABSIRA_SHELL_RC=0 leaves them alone. The deploy scripts do
# not depend on it: scripts/lib.sh finds nvm, pnpm and uv itself, so a deploy over ssh
# (which reads no rc file) works either way.
#
# Versions are pinned here and in the repository, never "latest": NVM_VERSION,
# PM2_VERSION and UV_VERSION below (checked against GitHub, npm and PyPI on
# 2026-10-04), Node in .nvmrc, pnpm in package.json, Python in .python-version.
# A different version is a commit, or the variable of the same name for one run.

set -Eeo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

CHECK=false
case "${1:-}" in
--check) CHECK=true ;;
"") ;;
*) die "usage: install-toolchain.sh [--check]" ;;
esac

[[ $EUID -ne 0 ]] || die "Run as the application user, not root: the tools live in its home."
NVM_VERSION="${NVM_VERSION:-v0.40.8}"
PM2_VERSION="${PM2_VERSION:-7.0.4}"
UV_VERSION="${UV_VERSION:-0.12.23}"
NODE_VERSION="${NODE_VERSION:-$(tr -d '[:space:]' <"$ROOT_DIR/.nvmrc")}"
PNPM_VERSION="${PNPM_VERSION:-$(sed -n 's/.*"packageManager": *"pnpm@\([^"]*\)".*/\1/p' "$ROOT_DIR/package.json")}"
PYTHON_VERSION="${PYTHON_VERSION:-$(tr -d '[:space:]' <"$ROOT_DIR/apps/api/.python-version")}"
[[ -n "$NODE_VERSION" && -n "$PNPM_VERSION" && -n "$PYTHON_VERSION" ]] ||
	die "No Node version in .nvmrc, no pnpm in package.json or no Python in apps/api/.python-version."
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
UV_BIN="$HOME/.local/bin/uv"

# What would be done, or do it.
act() {
	local what="$1"
	shift
	if $CHECK; then
		log "would: $what"
	else
		log "$what"
		"$@"
	fi
}

nvm_sh() {
	# nvm.sh is not written for set -u, and this script does not use it either way.
	# shellcheck disable=SC1091
	. "$NVM_DIR/nvm.sh" --no-use
}

# ─── nvm ────────────────────────────────────────────────────────────
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
	ok "nvm present at $NVM_DIR"
else
	# PROFILE=/dev/null: the installer must not edit any rc file.
	act "install nvm $NVM_VERSION" bash -c \
		"curl -fsSL 'https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh' | PROFILE=/dev/null bash"
fi

# ─── Node, pnpm, pm2 ────────────────────────────────────────────────
if [[ -s "$NVM_DIR/nvm.sh" ]]; then
	nvm_sh
	if nvm ls --no-colors "$NODE_VERSION" >/dev/null 2>&1; then
		ok "Node $NODE_VERSION installed in nvm"
	else
		act "install Node $NODE_VERSION with nvm" nvm install "$NODE_VERSION"
	fi
	$CHECK || {
		nvm use "$NODE_VERSION" >/dev/null
		nvm alias default "$NODE_VERSION" >/dev/null
	}
	if [[ "$(pnpm --version 2>/dev/null || true)" == "$PNPM_VERSION" ]]; then
		ok "pnpm $PNPM_VERSION"
	else
		act "install pnpm $PNPM_VERSION" npm install -g "pnpm@$PNPM_VERSION"
	fi
	if [[ "$(pm2 --version 2>/dev/null || true)" == "$PM2_VERSION" ]]; then
		ok "pm2 $PM2_VERSION"
	else
		act "install pm2 $PM2_VERSION" npm install -g "pm2@$PM2_VERSION"
	fi
else
	log "would: install Node $NODE_VERSION, pnpm $PNPM_VERSION and pm2 $PM2_VERSION once nvm is there"
fi

# ─── uv and the Python it builds ────────────────────────────────────
if [[ -x "$UV_BIN" && "$("$UV_BIN" --version 2>/dev/null | awk '{print $2}')" == "$UV_VERSION" ]]; then
	ok "uv $UV_VERSION"
else
	# UV_NO_MODIFY_PATH: no rc file is touched; scripts/lib.sh puts ~/.local/bin on the PATH.
	act "install uv $UV_VERSION" bash -c \
		"curl -LsSf 'https://astral.sh/uv/${UV_VERSION}/install.sh' | UV_NO_MODIFY_PATH=1 sh"
fi
if [[ -x "$UV_BIN" ]]; then
	if UV_PYTHON_PREFERENCE=only-managed "$UV_BIN" python find "$PYTHON_VERSION" >/dev/null 2>&1; then
		ok "Python $PYTHON_VERSION built by uv"
	else
		act "install Python $PYTHON_VERSION with uv (never the system Python)" \
			env UV_PYTHON_PREFERENCE=only-managed "$UV_BIN" python install "$PYTHON_VERSION"
	fi
else
	log "would: install Python $PYTHON_VERSION with uv once uv is there"
fi

# ─── The user's shell ───────────────────────────────────────────────
# One marked block per rc file, replaced on every run; nothing else of the file is touched.
RC_BEGIN="# >>> tabsira toolchain (deploy/install-toolchain.sh) >>>"
RC_END="# <<< tabsira toolchain <<<"
# shellcheck disable=SC2016  # expanded by the user's shell, not here
RC_BODY='export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac'
write_rc_section() {
	local rc="$1" tmp
	tmp="$(mktemp)"
	awk -v b="$RC_BEGIN" -v e="$RC_END" '$0 == b { skip = 1; next } $0 == e { skip = 0; next } !skip { print }' "$rc" >"$tmp"
	printf '\n%s\n%s\n%s\n' "$RC_BEGIN" "$RC_BODY" "$RC_END" >>"$tmp"
	cat "$tmp" >"$rc"
	rm -f "$tmp"
}
if [[ "${TABSIRA_SHELL_RC:-1}" == 1 ]]; then
	for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
		[[ -f "$rc" ]] || continue
		if $CHECK; then
			if grep -qxF "$RC_BEGIN" "$rc"; then
				ok "$rc loads nvm and ~/.local/bin"
			else
				log "would: add the nvm and ~/.local/bin section to $rc"
			fi
		else
			write_rc_section "$rc"
			ok "$rc loads nvm and ~/.local/bin (open a new shell, or: source $rc)"
		fi
	done
fi

if $CHECK; then
	ok "Check complete: nothing was installed."
else
	ok "Toolchain ready for $(id -un): nvm, Node $NODE_VERSION, pnpm $PNPM_VERSION, pm2 $PM2_VERSION, uv $UV_VERSION, Python $PYTHON_VERSION."
fi
