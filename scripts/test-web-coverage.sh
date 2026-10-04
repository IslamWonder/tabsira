#!/usr/bin/env bash
# Web tests with the 100 % coverage threshold and an HTML report
# (part of make coverage). apps/web does not exist until the design gate is
# passed, so while it is absent this skips with a notice, like test.sh and
# lint.sh. Once apps/web exists the stub fails until the web engineer
# replaces it: a missing coverage run must never read as a pass.
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
if [[ ! -f "$REPO_ROOT/apps/web/package.json" ]]; then
	skip "apps/web does not exist yet; no web coverage to measure"
	exit 0
fi
not_implemented "web coverage" "apps/web exists but its coverage run is not wired up."
