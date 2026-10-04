#!/usr/bin/env bash
# Run the detector service with reload, bound to loopback (VISION_HOST and VISION_PORT from the root .env).
#
# Usage: scripts/dev-vision.sh

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

load_env
[[ -d "$REPO_ROOT/services/vision/weights" ]] || warn "no weights yet: run services/vision/scripts/fetch-weights.sh"

cd "$REPO_ROOT/services/vision"
exec uv run uvicorn vision.main:create_app --factory --reload \
	--host "${VISION_HOST:-127.0.0.1}" --port "${VISION_PORT:-8100}"
