#!/usr/bin/env bash
# Helpers shared by every script in scripts/ and jenkins/.
# Source it after the script's own `set -euo pipefail`:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#
# Written for bash 3.2 (macOS /bin/bash) as well as bash 4+: no mapfile, no
# associative arrays, no GNU-only flags in anything the make targets run.
# Linux-only helpers (apt, os-release) are used by the provisioning scripts only.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT

# ─── Virtual-env hygiene ────────────────────────────────────────────
# Scripts cd into apps/api and services/vision, which have their own .venv. An
# outer VIRTUAL_ENV makes uv warn that it does not match the project environment.
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
	unset VIRTUAL_ENV
fi

# ─── The application user's own tools, on a server ──────────────────
# On the application host the user's uv sits in ~/.local/bin and its Node, pnpm and
# pm2 in nvm (deploy/install-toolchain.sh). A deploy over ssh reads no rc file and
# the login shell may be zsh, so find them here. /etc/tabsira/deploy.env exists on
# the servers only (deploy/provision-app.sh writes it): development machines keep
# whatever PATH they have.
if [[ -f /etc/tabsira/deploy.env ]]; then
	if [[ -d "$HOME/.local/bin" && ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
		export PATH="$HOME/.local/bin:$PATH"
	fi
	if [[ -z "${NODE_HOME:-}" && -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
		export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
		# nvm.sh is not written for set -u.
		_tabsira_nounset=0
		if [[ $- == *u* ]]; then
			_tabsira_nounset=1
			set +u
		fi
		# shellcheck disable=SC1091
		. "$NVM_DIR/nvm.sh" --no-use
		nvm use --silent default >/dev/null 2>&1 || true
		# nvm use leaves its bin where it is when PATH already has it: put it first.
		if [[ -n "${NVM_BIN:-}" ]]; then
			_tabsira_path=":$PATH:"
			_tabsira_path="${_tabsira_path//:$NVM_BIN:/:}"
			_tabsira_path="${_tabsira_path#:}"
			export PATH="$NVM_BIN:${_tabsira_path%:}"
			unset _tabsira_path
		fi
		if [[ $_tabsira_nounset == 1 ]]; then
			set -u
		fi
		unset _tabsira_nounset
	fi
fi

# ─── CI detection ───────────────────────────────────────────────────
is_ci() { [[ "${CI:-}" == "true" || "${CI:-}" == "1" ]]; }
is_jenkins() { [[ "${JENKINS_BUILD:-}" == "true" || "${JENKINS_BUILD:-}" == "1" ]]; }
in_ci() { is_ci || is_jenkins; }

have() { command -v "$1" >/dev/null 2>&1; }

is_macos() { [[ "$(uname -s)" == "Darwin" ]]; }
is_linux() { [[ "$(uname -s)" == "Linux" ]]; }

# ─── Colours and log helpers ────────────────────────────────────────
if [[ -t 1 ]]; then
	C_RESET=$'\033[0m'
	C_BOLD=$'\033[1m'
	C_RED=$'\033[31m'
	C_GREEN=$'\033[32m'
	C_YELLOW=$'\033[33m'
	C_BLUE=$'\033[34m'
else
	C_RESET=""
	C_BOLD=""
	C_RED=""
	C_GREEN=""
	C_YELLOW=""
	C_BLUE=""
fi

log() { printf '%s[tabsira]%s %s\n' "${C_BLUE}${C_BOLD}" "$C_RESET" "$*"; }
ok() { printf '%s[ ok ]%s %s\n' "${C_GREEN}${C_BOLD}" "$C_RESET" "$*"; }
warn() { printf '%s[warn]%s %s\n' "${C_YELLOW}${C_BOLD}" "$C_RESET" "$*" >&2; }
err() { printf '%s[err ]%s %s\n' "${C_RED}${C_BOLD}" "$C_RESET" "$*" >&2; }
die() {
	err "$*"
	exit 1
}

banner() {
	log "──────────────────────────────────────────────────────"
	log "$1"
	log "──────────────────────────────────────────────────────"
}

# An absent app or tool is not a failure of the thing being checked.
skip() { warn "skipped: $*"; }

# A make target whose feature is not built yet. It fails on purpose: a stub that
# exited 0 would show green for work nobody has done.
not_implemented() {
	err "$1 is not implemented yet. $2"
	exit 1
}

# Every shell script in the repository, one path per line, relative to the root:
# scripts/, jenkins/, deploy/, docker/ and anything under services/ and apps/.
list_shell_files() {
	(cd "$REPO_ROOT" && find scripts jenkins deploy docker services apps \
		-type d \( -name node_modules -o -name .venv \) -prune -o \
		-type f \( -name '*.sh' -o -path 'scripts/git-hooks/*' \) -print 2>/dev/null | sort)
}

require_cmd() {
	have "$1" || die "$1 is not installed. $2"
}

# ─── The user's own tools, whatever shell started us ────────────────
# On a server the app user's uv sits in ~/.local/bin and its Node in nvm, and a
# deploy started over ssh or by Jenkins reads no shell rc file at all. So find
# them here rather than in anybody's .zshrc or .bashrc.
if [[ -n "${NODE_HOME:-}" ]]; then
	export PATH="${NODE_HOME}/bin:${PATH}"
fi
if [[ -d "$HOME/.local/bin" && ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
	export PATH="$HOME/.local/bin:$PATH"
fi
if [[ -d "$HOME/.local/share/pnpm" && ":$PATH:" != *":$HOME/.local/share/pnpm:"* ]]; then
	export PNPM_HOME="$HOME/.local/share/pnpm"
	export PATH="$PNPM_HOME:$PATH"
fi

_tbs_node_major() { node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0; }

# nvm's default Node is used only when the Node already on PATH is missing or
# older than the one the repository needs, so a developer's own Node 24 (from
# any version manager) is never replaced by a stale nvm default.
if [[ -z "${NODE_HOME:-}" && -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]] &&
	(! have node || [[ "$(_tbs_node_major)" -lt 24 ]]); then
	export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
	_tbs_nounset=0
	if [[ $- == *u* ]]; then
		_tbs_nounset=1
		set +u # nvm.sh is not written for set -u
	fi
	# shellcheck disable=SC1091
	. "$NVM_DIR/nvm.sh" --no-use
	nvm use --silent default >/dev/null 2>&1 || true
	if [[ $_tbs_nounset == 1 ]]; then
		set -u
	fi
	unset _tbs_nounset
fi

# ─── pnpm version management ────────────────────────────────────────
# Make the active pnpm match the packageManager field of the root package.json,
# through corepack when it differs.
ensure_pnpm_version() {
	have node || {
		warn "node not found; cannot verify the pnpm version"
		return 0
	}
	local required current
	required="$(cd "$REPO_ROOT" && node -p "(require('./package.json').packageManager || '').split('@')[1] || ''" 2>/dev/null || true)"
	if [[ -z "$required" ]]; then
		warn "no pnpm version pinned in package.json; skipping the pnpm version check"
		return 0
	fi
	have corepack && corepack enable >/dev/null 2>&1 || true
	current="$(pnpm --version 2>/dev/null || echo none)"
	if [[ "$current" == "$required" ]]; then
		ok "pnpm is at the pinned version $current"
		return 0
	fi
	log "pnpm is $current, package.json pins $required"
	if have corepack && corepack prepare "pnpm@$required" --activate; then
		ok "pnpm is now $(pnpm --version 2>/dev/null || echo unknown)"
	else
		warn "could not switch pnpm to $required; install it with: npm install -g pnpm@$required"
	fi
}

# ─── .env helpers ───────────────────────────────────────────────────
# Load the repo-root .env, except in CI where the pipeline injects the values.
load_env() {
	if in_ci; then
		return 0
	fi
	if [[ -f "$REPO_ROOT/.env" ]]; then
		set -a
		# shellcheck disable=SC1091
		. "$REPO_ROOT/.env"
		set +a
	else
		warn ".env not found at $REPO_ROOT/.env (run: bash scripts/setup-db.sh)"
	fi
}

# KEY from an env file: the last assignment wins, surrounding quotes dropped.
# Prints nothing when the file or the key is missing.
env_value() {
	local file="$1" key="$2"
	[[ -f "$file" ]] || return 0
	{ grep -E "^${key}=" "$file" || true; } | tail -n 1 | cut -d= -f2- |
		sed -E "s/^\"(.*)\"\$/\\1/; s/^'(.*)'\$/\\1/"
}

# Set KEY=VALUE in an env file: replace the line or append one. Written in
# place (cat >) so the file keeps its owner and mode. VALUE must not need quoting.
env_put() {
	local file="$1" key="$2" value="$3" tmp
	tmp="$(mktemp)"
	if grep -qE "^${key}=" "$file"; then
		awk -v k="$key" -v v="$value" 'index($0, k "=") == 1 { print k "=" v; next } { print }' "$file" >"$tmp"
	else
		cat "$file" >"$tmp"
		if [[ -s "$tmp" && -n "$(tail -c 1 "$tmp")" ]]; then
			echo >>"$tmp"
		fi
		printf '%s=%s\n' "$key" "$value" >>"$tmp"
	fi
	cat "$tmp" >"$file"
	rm -f "$tmp"
}

# ─── Linux provisioning helpers (Debian family) ─────────────────────
as_root() {
	if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

# Ubuntu and its derivatives (Linux Mint reports ID=linuxmint, ID_LIKE=ubuntu).
# Sets OS_CODENAME to the Ubuntu codename the apt repositories are named after.
require_ubuntu() {
	[[ -r /etc/os-release ]] || die "this script targets Ubuntu; /etc/os-release is missing"
	local id id_like codename
	# shellcheck disable=SC1091
	id="$(. /etc/os-release && echo "${ID:-}")"
	# shellcheck disable=SC1091
	id_like="$(. /etc/os-release && echo "${ID_LIKE:-}")"
	# shellcheck disable=SC1091
	codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}")"
	if [[ "$id" != "ubuntu" && " $id_like " != *" ubuntu "* ]]; then
		die "this script targets Ubuntu or a derivative (found: $id)"
	fi
	[[ -n "$codename" ]] || die "cannot tell the Ubuntu codename from /etc/os-release"
	OS_CODENAME="$codename"
	export OS_CODENAME
	log "Ubuntu base: $OS_CODENAME"
}

require_sudo() {
	[[ $EUID -eq 0 ]] && return 0
	have sudo || die "sudo is required"
}

apt_install() {
	local missing=() p
	for p in "$@"; do
		dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
	done
	if [[ ${#missing[@]} -gt 0 ]]; then
		log "Installing: ${missing[*]}"
		as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
	else
		ok "Already installed: $*"
	fi
}
