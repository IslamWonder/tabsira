#!/usr/bin/env bash
# Install the command-line tools the format, lint and security scripts call.
#
# Usage: scripts/install-quality-tools.sh [tool ...]     (default: every tool)
#   tools: shellcheck shfmt gitleaks typos trivy osv-scanner
#
# Each tool is a pinned release from its own GitHub project, so a laptop, the CI
# image and a server run the same version. Checksums are verified where the
# project publishes them. To move a pin, check the project's latest release
# first and change the line below; never guess a version.
#
# Environment:
#   INSTALL_DIR  where the binaries go (default /usr/local/bin; sudo is used when
#                the directory is not writable)
#   <TOOL>_VERSION overrides one pin, e.g. SHFMT_VERSION=3.14.1
#
# Linux and macOS, x86_64 and arm64. Python-based scanners (semgrep, bandit,
# pip-audit) are not installed here: scripts/audit.sh runs them through uvx.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib.sh"

# Latest releases as of 2026-10-04, read from each project's GitHub releases.
SHELLCHECK_VERSION="${SHELLCHECK_VERSION:-0.11.0}"
SHFMT_VERSION="${SHFMT_VERSION:-3.14.1}"
GITLEAKS_VERSION="${GITLEAKS_VERSION:-8.30.1}"
TYPOS_VERSION="${TYPOS_VERSION:-1.50.3}"
TRIVY_VERSION="${TRIVY_VERSION:-0.75.0}"
OSV_SCANNER_VERSION="${OSV_SCANNER_VERSION:-2.6.0}"

INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
ALL_TOOLS="shellcheck shfmt gitleaks typos trivy osv-scanner"

require_cmd curl "Install curl first."
have tar || die "tar is required"

case "$(uname -s)" in
Linux) OS="linux" ;;
Darwin) OS="darwin" ;;
*) die "unsupported system: $(uname -s)" ;;
esac
case "$(uname -m)" in
x86_64 | amd64) ARCH="amd64" ;;
aarch64 | arm64) ARCH="arm64" ;;
*) die "unsupported CPU: $(uname -m)" ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fetch() { curl -fsSL --retry 3 -o "$2" "$1"; }

sha256_of() {
	if have sha256sum; then
		sha256sum "$1" | cut -d' ' -f1
	else
		shasum -a 256 "$1" | cut -d' ' -f1
	fi
}

# verify FILE CHECKSUMS_FILE NAME: the checksum list names the file NAME.
verify() {
	local file="$1" sums="$2" name="$3" want
	want="$(grep -E "[ *]${name}\$" "$sums" | head -n 1 | cut -d' ' -f1)"
	[[ -n "$want" ]] || die "no checksum for $name in the published list"
	[[ "$(sha256_of "$file")" == "$want" ]] || die "checksum mismatch for $name"
}

place() {
	local src="$1" name="$2"
	if [[ -w "$INSTALL_DIR" ]]; then
		install -m 0755 "$src" "$INSTALL_DIR/$name"
	else
		as_root install -m 0755 "$src" "$INSTALL_DIR/$name"
	fi
	ok "$name installed to $INSTALL_DIR"
}

# What `<tool> --version` prints must contain the pinned version.
has_version() {
	local tool="$1" want="$2" out
	have "$tool" || return 1
	out="$("$tool" --version 2>&1 || "$tool" version 2>&1 || true)"
	[[ "$out" == *"$want"* ]]
}

install_shfmt() {
	local v="$SHFMT_VERSION"
	fetch "https://github.com/mvdan/sh/releases/download/v${v}/shfmt_v${v}_${OS}_${ARCH}" "$WORK/shfmt"
	place "$WORK/shfmt" shfmt
}

install_shellcheck() {
	local v="$SHELLCHECK_VERSION" cpu="x86_64"
	[[ "$ARCH" == "arm64" ]] && cpu="aarch64"
	fetch "https://github.com/koalaman/shellcheck/releases/download/v${v}/shellcheck-v${v}.${OS}.${cpu}.tar.gz" "$WORK/shellcheck.tgz"
	tar -xzf "$WORK/shellcheck.tgz" -C "$WORK"
	place "$WORK/shellcheck-v${v}/shellcheck" shellcheck
}

install_gitleaks() {
	local v="$GITLEAKS_VERSION" cpu="x64" name
	[[ "$ARCH" == "arm64" ]] && cpu="arm64"
	name="gitleaks_${v}_${OS}_${cpu}.tar.gz"
	fetch "https://github.com/gitleaks/gitleaks/releases/download/v${v}/${name}" "$WORK/$name"
	fetch "https://github.com/gitleaks/gitleaks/releases/download/v${v}/gitleaks_${v}_checksums.txt" "$WORK/gitleaks.sums"
	verify "$WORK/$name" "$WORK/gitleaks.sums" "$name"
	tar -xzf "$WORK/$name" -C "$WORK" gitleaks
	place "$WORK/gitleaks" gitleaks
}

install_typos() {
	local v="$TYPOS_VERSION" triple
	case "$OS-$ARCH" in
	linux-amd64) triple="x86_64-unknown-linux-musl" ;;
	linux-arm64) triple="aarch64-unknown-linux-musl" ;;
	darwin-amd64) triple="x86_64-apple-darwin" ;;
	darwin-arm64) triple="aarch64-apple-darwin" ;;
	esac
	fetch "https://github.com/crate-ci/typos/releases/download/v${v}/typos-v${v}-${triple}.tar.gz" "$WORK/typos.tgz"
	mkdir -p "$WORK/typos"
	tar -xzf "$WORK/typos.tgz" -C "$WORK/typos"
	place "$WORK/typos/typos" typos
}

install_trivy() {
	local v="$TRIVY_VERSION" label name
	case "$OS-$ARCH" in
	linux-amd64) label="Linux-64bit" ;;
	linux-arm64) label="Linux-ARM64" ;;
	darwin-amd64) label="macOS-64bit" ;;
	darwin-arm64) label="macOS-ARM64" ;;
	esac
	name="trivy_${v}_${label}.tar.gz"
	fetch "https://github.com/aquasecurity/trivy/releases/download/v${v}/${name}" "$WORK/$name"
	fetch "https://github.com/aquasecurity/trivy/releases/download/v${v}/trivy_${v}_checksums.txt" "$WORK/trivy.sums"
	verify "$WORK/$name" "$WORK/trivy.sums" "$name"
	tar -xzf "$WORK/$name" -C "$WORK" trivy
	place "$WORK/trivy" trivy
}

# osv-scanner 2.x or later: 1.x cannot read uv.lock, which audit.sh scans.
install_osv_scanner() {
	local v="$OSV_SCANNER_VERSION" name="osv-scanner_${OS}_${ARCH}"
	fetch "https://github.com/google/osv-scanner/releases/download/v${v}/${name}" "$WORK/$name"
	fetch "https://github.com/google/osv-scanner/releases/download/v${v}/osv-scanner_SHA256SUMS" "$WORK/osv.sums"
	verify "$WORK/$name" "$WORK/osv.sums" "$name"
	place "$WORK/$name" osv-scanner
}

pinned_version() {
	case "$1" in
	shellcheck) echo "$SHELLCHECK_VERSION" ;;
	shfmt) echo "$SHFMT_VERSION" ;;
	gitleaks) echo "$GITLEAKS_VERSION" ;;
	typos) echo "$TYPOS_VERSION" ;;
	trivy) echo "$TRIVY_VERSION" ;;
	osv-scanner) echo "$OSV_SCANNER_VERSION" ;;
	*) die "unknown tool: $1 (known: $ALL_TOOLS)" ;;
	esac
}

TOOLS=("$@")
if [[ ${#TOOLS[@]} -eq 0 ]]; then
	# shellcheck disable=SC2206  # ALL_TOOLS is a fixed list of words
	TOOLS=($ALL_TOOLS)
fi

log "Installing quality tools: ${TOOLS[*]}"
for tool in "${TOOLS[@]}"; do
	want="$(pinned_version "$tool")"
	if has_version "$tool" "$want"; then
		ok "$tool $want already installed"
		continue
	fi
	log "Installing $tool $want"
	"install_${tool//-/_}"
done

for tool in "${TOOLS[@]}"; do
	want="$(pinned_version "$tool")"
	has_version "$tool" "$want" ||
		warn "$tool on PATH is not $want; is $INSTALL_DIR first in PATH?"
done
ok "Quality tools ready"
