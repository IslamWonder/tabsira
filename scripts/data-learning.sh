#!/usr/bin/env bash
# Import the world ontology and the learning path into the database.
#
# Usage:
#   scripts/data-learning.sh [ontology | masar | all] [arguments for the importer]
#
# data.sh sources this file and calls import_ontology and import_masar itself:
#   source "$SCRIPT_DIR/data-learning.sh"
#   import_ontology
#   import_masar
#
# import_ontology  reads data/world-ontology.xlsx (never modified), refreshes the generated
#                  data/ontology/world-ontology.json and loads corpus.ontology_entities.
# import_masar     checks that data/masar/tabsira-masar-1.0.json is what docs/spec/masar.md
#                  produces, then imports every data/masar/*.json, oldest first. The first
#                  version becomes the active one; a later release waits unless the importer
#                  is given --activate (the last file imported is then the active one).
#
# Both are safe to run again: the same files change nothing. Run `make migrate` first.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

# What the first release of the learning path must hold (docs/LEARNING_PATH.md).
MASAR_FIRST_VERSION="tabsira-masar-1.0"
MASAR_FIRST_DOMAINS=16
MASAR_FIRST_UNITS=96

api() {
	require_cmd uv "Run: make install"
	(cd "$REPO_ROOT/apps/api" && uv run --quiet python -m "$@")
}

import_ontology() {
	log "Importing the world ontology..."
	api src.cli.import_ontology "$@"
	ok "World ontology imported"
}

import_masar() {
	local file name
	local -a counts

	log "Checking that the learning path data is current..."
	api src.cli.parse_masar --check --expect-domains "$MASAR_FIRST_DOMAINS" --expect-units "$MASAR_FIRST_UNITS"

	log "Importing the learning path..."
	# Version order, numeric: tabsira-masar-1.0, then 1.1, then 1.10 (portable: no sort -V).
	while IFS= read -r file; do
		name="${file%.json}"
		counts=()
		if [[ "$name" == "$MASAR_FIRST_VERSION" ]]; then
			counts=(--expect-domains "$MASAR_FIRST_DOMAINS" --expect-units "$MASAR_FIRST_UNITS")
		fi
		api src.cli.import_masar --source "$REPO_ROOT/data/masar/$file" "${counts[@]+"${counts[@]}"}" "$@"
	done < <(cd "$REPO_ROOT/data/masar" && shopt -s nullglob && printf '%s\n' *.json | sort -t. -k1,1 -k2,2n)
	ok "Learning path imported"
}

# Run directly (not sourced): do what was asked.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
	what="${1:-all}"
	[[ $# -gt 0 ]] && shift
	case "$what" in
	ontology) import_ontology "$@" ;;
	masar) import_masar "$@" ;;
	all)
		import_ontology
		import_masar "$@"
		;;
	*) die "usage: scripts/data-learning.sh [ontology | masar | all] [importer arguments]" ;;
	esac
fi
