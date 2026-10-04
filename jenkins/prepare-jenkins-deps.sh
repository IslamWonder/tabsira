#!/usr/bin/env bash
# What a Jenkins agent needs to run the TABSIRA pipeline, on Ubuntu 24.04 or 26.04.
#
# Usage:
#   sudo bash jenkins/prepare-jenkins-deps.sh           install what is missing (one-time agent setup)
#   bash jenkins/prepare-jenkins-deps.sh --check        verify only; the pipeline's Prepare stage runs this
#
# Installs, in this order:
#   1. base packages: curl, git, make, openssl, unzip and certificates
#   2. postgresql-client-18 from PGDG: pg_dump 16 (Ubuntu's) refuses the 18 server
#   3. the quality tools, pinned and checksum-verified: scripts/install-quality-tools.sh
#   4. uv, at the version pinned below
# Docker and the agent user's membership of the docker group are verified, never
# installed: adding a user to a group from inside a build does not reach that
# build (group membership is fixed when the session starts), so a script that
# tried would produce a confusing pass-then-fail. See docs/JENKINS_SETUP.md.
# Node 24 comes from the NodeJS tool of Jenkins (NODE_TOOL_NAME), not from here.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

# Latest uv release on 2026-10-04 (github.com/astral-sh/uv/releases); apps/api/uv.lock
# and services/vision/uv.lock were checked with it (`uv lock --check`).
UV_VERSION="${UV_VERSION:-0.12.23}"
PG_CLIENT_VERSION="${PG_CLIENT_VERSION:-18}"

MODE="install"
case "${1:-}" in
"") ;;
--check) MODE="check" ;;
*) die "usage: jenkins/prepare-jenkins-deps.sh [--check]" ;;
esac

# ─── check ──────────────────────────────────────────────────────────
# Tools without which the build cannot pass are required; the audit's own tools
# are advisory, so a missing one is a warning.
cmd_check() {
	local missing=() tool
	for tool in git curl openssl docker uv node shellcheck shfmt gitleaks; do
		if have "$tool"; then
			ok "$tool: $(command -v "$tool")"
		else
			err "$tool is missing"
			missing+=("$tool")
		fi
	done
	for tool in psql typos trivy osv-scanner; do
		if have "$tool"; then
			ok "$tool: $(command -v "$tool")"
		else
			warn "$tool is missing (advisory: the audit or a migration step skips what needs it)"
		fi
	done
	if have node && [[ "$(_tbs_node_major)" -lt 24 ]]; then
		err "node $(node --version) is too old: Node 24 is required (NODE_TOOL_NAME names the Jenkins tool that provides it)"
		missing+=("node-24")
	fi
	if [[ ${#missing[@]} -gt 0 ]]; then
		die "Missing on this agent: ${missing[*]}. Run once: sudo bash jenkins/prepare-jenkins-deps.sh (docs/JENKINS_SETUP.md)."
	fi
	ok "This agent can run the pipeline."
}

# ─── install ────────────────────────────────────────────────────────
install_postgres_client() {
	if dpkg -s "postgresql-client-${PG_CLIENT_VERSION}" >/dev/null 2>&1; then
		ok "postgresql-client-${PG_CLIENT_VERSION} already installed"
		return 0
	fi
	if ! grep -rqs "apt.postgresql.org/pub/repos/apt" /etc/apt/sources.list /etc/apt/sources.list.d; then
		log "Adding the PGDG apt repository for $OS_CODENAME"
		as_root install -m 0755 -d /etc/apt/keyrings
		curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc |
			as_root gpg --dearmor --yes -o /etc/apt/keyrings/postgresql.gpg
		as_root chmod a+r /etc/apt/keyrings/postgresql.gpg
		echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt ${OS_CODENAME}-pgdg main" |
			as_root tee /etc/apt/sources.list.d/pgdg.list >/dev/null
		as_root apt-get update -y
	fi
	apt_install "postgresql-client-${PG_CLIENT_VERSION}"
}

install_uv() {
	if have uv && [[ "$(uv --version 2>/dev/null)" == "uv ${UV_VERSION}"* ]]; then
		ok "uv ${UV_VERSION} already installed"
		return 0
	fi
	log "Installing uv ${UV_VERSION} into /usr/local/bin"
	curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" |
		as_root env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
	ok "$(uv --version)"
}

cmd_install() {
	require_ubuntu
	require_sudo

	banner "1/4 Base packages"
	as_root apt-get update -y || warn "apt-get update reported errors; continuing"
	apt_install ca-certificates curl gnupg git make openssl unzip

	banner "2/4 PostgreSQL client ${PG_CLIENT_VERSION}"
	install_postgres_client

	banner "3/4 Quality tools"
	bash "$ROOT_DIR/scripts/install-quality-tools.sh"

	banner "4/4 uv"
	install_uv

	banner "Docker"
	if have docker && docker info >/dev/null 2>&1; then
		ok "docker answers for this user"
	else
		warn "docker is missing, or this user cannot reach it. Install the Docker engine, then:"
		warn "  sudo usermod -aG docker jenkins && sudo systemctl restart jenkins"
	fi
	cmd_check
}

case "$MODE" in
check) cmd_check ;;
install) cmd_install ;;
esac
