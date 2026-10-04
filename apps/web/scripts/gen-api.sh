#!/usr/bin/env bash
# Regenerate the typed API client from the API's own OpenAPI document
# (pnpm --filter @tabsira/web gen:api, or pnpm gen:api at the root).
#
#   1. Build the FastAPI app with its factory, create_app() in
#      apps/api/src/main.py, and write app.openapi() to src/lib/api/openapi.json.
#      Nothing is served and no database connection is opened.
#   2. Generate src/lib/api/schema.d.ts from it with openapi-typescript.
#
# Both files are committed. Run this after any change to the API's routes or
# schemas: the web never writes an API type by hand (AGENTS.md).
set -euo pipefail

WEB_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$WEB_DIR/../.." &>/dev/null && pwd)"
OUT_DIR="$WEB_DIR/src/lib/api"

if ! command -v uv >/dev/null 2>&1; then
	echo "uv is not installed. Run: make install" >&2
	exit 1
fi

# An outer virtual environment makes uv warn that it is not the project's.
unset VIRTUAL_ENV

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

(
	cd "$REPO_ROOT/apps/api"
	uv run --quiet python -c '
import json
import sys

from src.main import create_app

json.dump(create_app().openapi(), sys.stdout, ensure_ascii=False, indent=2)
sys.stdout.write("\n")
'
) >"$tmp"

# cat, not cp: the file keeps ordinary permissions instead of mktemp's 0600.
cat "$tmp" >"$OUT_DIR/openapi.json"
cd "$WEB_DIR"
pnpm exec openapi-typescript src/lib/api/openapi.json --output src/lib/api/schema.d.ts
pnpm exec biome format --write src/lib/api/openapi.json src/lib/api/schema.d.ts >/dev/null
echo "Generated src/lib/api/openapi.json and src/lib/api/schema.d.ts"
