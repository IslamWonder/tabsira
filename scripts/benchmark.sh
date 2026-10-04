#!/usr/bin/env bash
# Compare AI providers, detectors and rerankers on the same scenes
# (make benchmark). Not built yet: the provider adapters and the scene set must
# exist first (DECISIONS.md, decision 4).
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
not_implemented "make benchmark" "The provider adapters and the benchmark scenes do not exist yet."
