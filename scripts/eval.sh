#!/usr/bin/env bash
# Gold scenes and the official contest cases (make eval). Not built yet: it
# needs the scan pipeline and the gold-scene set (docs/spec/master-prompt-v2.md,
# section 23).
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
not_implemented "make eval" "The scan pipeline and the gold scenes do not exist yet."
