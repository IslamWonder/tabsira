#!/usr/bin/env bash
# Start the whole stack with docker compose (make up). Not built yet: the
# compose file does not exist. Once one is added at the repository root this
# script runs it; until then it fails instead of pretending.
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$REPO_ROOT"
for file in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
	if [[ -f "$file" ]]; then
		require_cmd docker "Install Docker Engine or Docker Desktop."
		exec docker compose -f "$file" up --build
	fi
done
not_implemented "make up" "No compose file exists yet (the stack is described in docs/spec/master-prompt-v2.md, section 24)."
