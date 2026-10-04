#!/usr/bin/env bash
# HTTP checks against a running app (make smoke). Not built yet: it needs the
# health route and the rain scene (docs/spec/master-prompt-v2.md, section 23).
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
not_implemented "make smoke" "The health route and the rain scene do not exist yet."
