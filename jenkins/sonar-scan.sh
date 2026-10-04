#!/usr/bin/env bash
# Send this checkout to SonarQube with the coverage the test suites have just
# written, and wait for the quality gate. Called by the Jenkinsfile's SonarQube
# stage; what is analysed is set in sonar-project.properties.
#
# Usage: jenkins/sonar-scan.sh [--dry-run]
#   --dry-run  print what would be analysed, install and send nothing
#
# Configuration (defaults in jenkins/jenkins.env, never in this script):
#   SONAR_TOKEN                required; bound from the Jenkins credential, never printed
#   SONAR_HOST_URL             required; the address of the SonarQube server
#   SONAR_PROJECT_KEY          project key on the server (default tabsira)
#   SONAR_PROJECT_NAME         display name (default TABSIRA)
#   SONAR_QUALITYGATE_TIMEOUT  seconds to wait for the gate (default 600)
#   SONAR_SCANNER_CACHE        where the scanner is kept (default ~/.cache/sonar-scanner)
#
# The scanner is pinned and checked against its published SHA-256, and cached
# per version outside the workspace so a clean workspace does not throw it
# away. Its linux builds ship their own JRE, so the agent needs no Java.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ci-env.sh"

# Latest release of SonarSource/sonar-scanner-cli on 2026-10-04. The checksums
# are the ones SonarSource publishes next to each archive (<archive>.sha256).
SONAR_SCANNER_VERSION="8.1.0.6389"
SHA256_LINUX_X64="bb8f709f9cb73352f8d1260a3b3c506c0f41146754bc630762c126d795499d0b"
SHA256_LINUX_AARCH64="5e1c9328f4e261838de778c9e586ee608cca45ff7f0538108642219214628ba5"

DRY_RUN=false
case "${1:-}" in
"") ;;
--dry-run) DRY_RUN=true ;;
*) die "usage: jenkins/sonar-scan.sh [--dry-run]" ;;
esac

SONAR_PROJECT_KEY="${SONAR_PROJECT_KEY:-tabsira}"
SONAR_PROJECT_NAME="${SONAR_PROJECT_NAME:-TABSIRA}"
SONAR_QUALITYGATE_TIMEOUT="${SONAR_QUALITYGATE_TIMEOUT:-600}"
CACHE_DIR="${SONAR_SCANNER_CACHE:-${HOME}/.cache/sonar-scanner}"
PROPERTIES="$ROOT_DIR/sonar-project.properties"

cd "$ROOT_DIR"

# ─── Configuration ──────────────────────────────────────────────────
if ! $DRY_RUN; then
	[[ -n "${SONAR_HOST_URL:-}" ]] ||
		die "SONAR_HOST_URL is not set. Set it in jenkins/jenkins.env, on the Jenkins job or as a build parameter (see docs/JENKINS_SETUP.md)."
	[[ -n "${SONAR_TOKEN:-}" ]] ||
		die "SONAR_TOKEN is not set. Bind the Jenkins credential named by SONAR_CREDENTIALS_ID (see docs/JENKINS_SETUP.md)."
fi
HOST_URL="${SONAR_HOST_URL:-<SONAR_HOST_URL is not set>}"
HOST_URL="${HOST_URL%/}"

# ─── What exists ────────────────────────────────────────────────────
# The value of KEY in sonar-project.properties, on one line.
property() {
	{ grep -E "^$1=" "$PROPERTIES" || true; } | head -n 1 | cut -d= -f2-
}

# Keep the entries of a comma-separated list of paths that exist now. The
# scanner stops at a source directory that is missing; apps/web, for one, does
# not exist until the web app is built.
existing_paths() {
	local list="$1" entry kept=() dropped=()
	local IFS=,
	for entry in $list; do
		if [[ -e "$ROOT_DIR/$entry" ]]; then
			kept+=("$entry")
		else
			dropped+=("$entry")
		fi
	done
	[[ ${#dropped[@]} -eq 0 ]] || warn "not analysed, not there yet: ${dropped[*]}"
	printf '%s' "${kept[*]-}"
}

SOURCES="$(existing_paths "$(property sonar.sources)")"
TESTS="$(existing_paths "$(property sonar.tests)")"
[[ -n "$SOURCES" ]] || die "none of the directories in sonar.sources exists."

# A missing report is not fatal, since the analysis is still worth having, but
# SonarQube would show that side at 0 % coverage, so say why.
reports=(apps/api/coverage/coverage.xml services/vision/coverage/coverage.xml)
[[ -d apps/web ]] && reports+=(apps/web/coverage/lcov.info)
for report in "${reports[@]}"; do
	[[ -f "$report" ]] || warn "No coverage report at $report; SonarQube will show that side as uncovered."
done

# The root package.json carries the release version; SonarQube's default
# new-code period ("previous version") needs it to move.
PROJECT_VERSION=""
if have node; then
	PROJECT_VERSION="$(node -p "require('./package.json').version" 2>/dev/null || true)"
fi

ARGS=(
	"-Dsonar.host.url=$HOST_URL"
	"-Dsonar.projectKey=$SONAR_PROJECT_KEY"
	"-Dsonar.projectName=$SONAR_PROJECT_NAME"
	"-Dsonar.sources=$SOURCES"
	"-Dsonar.tests=$TESTS"
	"-Dsonar.qualitygate.wait=true"
	"-Dsonar.qualitygate.timeout=$SONAR_QUALITYGATE_TIMEOUT"
)
[[ -z "$PROJECT_VERSION" ]] || ARGS+=("-Dsonar.projectVersion=$PROJECT_VERSION")

if $DRY_RUN; then
	log "Dry run: nothing is installed or sent. The scanner would be called with:"
	printf '  %s\n' "${ARGS[@]}"
	exit 0
fi

# ─── The scanner ────────────────────────────────────────────────────
case "$(uname -m)" in
x86_64 | amd64)
	ARCH="x64"
	SCANNER_SHA256="$SHA256_LINUX_X64"
	;;
aarch64 | arm64)
	ARCH="aarch64"
	SCANNER_SHA256="$SHA256_LINUX_AARCH64"
	;;
*) die "no pinned SonarScanner for this CPU: $(uname -m)" ;;
esac
is_linux || die "the pinned SonarScanner is the Linux build; run this on a Linux agent."

SCANNER_NAME="sonar-scanner-${SONAR_SCANNER_VERSION}-linux-${ARCH}"
SCANNER_HOME="$CACHE_DIR/$SCANNER_NAME"

install_scanner() {
	if [[ -x "$SCANNER_HOME/bin/sonar-scanner" ]]; then
		ok "SonarScanner ${SONAR_SCANNER_VERSION} already cached"
		return 0
	fi

	log "Installing SonarScanner ${SONAR_SCANNER_VERSION} into $CACHE_DIR"
	mkdir -p "$CACHE_DIR"
	local tmp zip
	tmp="$(mktemp -d "$CACHE_DIR/.install.XXXXXX")"
	zip="$tmp/scanner.zip"
	curl -fsSL --connect-timeout 30 --retry 3 --retry-delay 5 -o "$zip" \
		"https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux-${ARCH}.zip"
	echo "${SCANNER_SHA256}  ${zip}" | sha256sum --check --quiet - ||
		die "The SonarScanner download does not match its pinned checksum."

	if have unzip; then
		unzip -q "$zip" -d "$tmp"
	else
		# Python's zipfile drops the executable bits, so put them back.
		python3 -m zipfile -e "$zip" "$tmp"
		chmod -R u+x "$tmp/$SCANNER_NAME/bin" "$tmp/$SCANNER_NAME/jre/bin"
	fi

	# Two builds installing at once: the loser's rename fails and it uses the
	# winner's copy, which is the same verified archive.
	mv -T "$tmp/$SCANNER_NAME" "$SCANNER_HOME" 2>/dev/null || true
	rm -rf "$tmp"
	[[ -x "$SCANNER_HOME/bin/sonar-scanner" ]] || die "SonarScanner is not executable at $SCANNER_HOME."
	ok "SonarScanner ${SONAR_SCANNER_VERSION} installed"
}

install_scanner

log "Analysing ${SONAR_PROJECT_KEY} on ${HOST_URL}${PROJECT_VERSION:+ (version ${PROJECT_VERSION})}"
log "  sources: $SOURCES"
log "  tests:   ${TESTS:-none}"
# SONAR_TOKEN is read from the environment by the scanner, so it never appears
# on a command line or in the build log.
"$SCANNER_HOME/bin/sonar-scanner" "${ARGS[@]}"

ok "SonarQube analysis passed the quality gate: ${HOST_URL}/dashboard?id=${SONAR_PROJECT_KEY}"
