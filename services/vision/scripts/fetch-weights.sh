#!/usr/bin/env bash
# Download the detector weights into services/vision/weights/: the checkpoint and
# the text encoder that turns a vocabulary into classes. Files that are already
# there are kept, so running it twice downloads nothing.
#
# Usage: scripts/fetch-weights.sh [checkpoint]
#   checkpoint  yoloe-11s-seg.pt (default) or yolov8s-worldv2.pt; without an
#               argument DETECTOR_MODEL from the environment or the root .env decides.
#
# YOLOE needs about 630 MB in all (checkpoint 28 MB, MobileCLIP text encoder 600 MB).

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

command -v uv >/dev/null 2>&1 || {
	echo "[err ] uv is not installed. See https://docs.astral.sh/uv/" >&2
	exit 1
}

# An outer virtual environment makes uv warn that it does not match this project's.
unset VIRTUAL_ENV

if [[ $# -gt 0 ]]; then
	export DETECTOR_MODEL="$1"
fi

cd "$SERVICE_DIR"
exec uv run python -m vision.weights
