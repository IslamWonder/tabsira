#!/usr/bin/env bash
# Import the corpora, the ontology and the learning path, and build the indexes
# (make data). Not built yet: the importer lives in apps/api and checks the
# Quran text against the Tanzil Uthmani edition (DECISIONS.md, decision 6).
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
not_implemented "make data" "The corpus, ontology and learning-path importers do not exist yet."
