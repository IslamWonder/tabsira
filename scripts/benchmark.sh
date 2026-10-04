#!/usr/bin/env bash
# Compare the vision models on the gold scenes (make benchmark): each candidate
# of apps/api/src/evaluation/benchmark.py describes every scene of
# apps/api/tests/evaluation/scenes/, and the measured result is written to
# docs/BENCHMARK.md (raw answers in apps/api/tests/evaluation/results/, not
# committed). Detectors and rerankers join the same command when they exist.
#
# It calls the real providers with the keys of the root .env and costs money
# (about one dollar for the default matrix; --max-cost caps it). The vision
# service should run (make dev, or services/vision: uv run vision); without it
# the scenes are described without boxes and the report says so.
#
# Usage: scripts/benchmark.sh [--runs N] [--cells a,b] [--scenes x,y] ...
#        (see: cd apps/api && uv run python -m src.cli.benchmark --help)
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

have uv || die "uv is not installed. Run: make install"
cd "$REPO_ROOT/apps/api"
uv run python -m src.cli.benchmark "$@"

# The report and the summary are generated; format them the way the checks want.
if have pnpm && [[ -d "$REPO_ROOT/node_modules" ]]; then
	cd "$REPO_ROOT"
	pnpm exec prettier --log-level warn --write docs/BENCHMARK.md
	pnpm exec biome format --write apps/api/tests/evaluation/results/*-summary.json >/dev/null
else
	warn "pnpm is missing: run 'make format' before committing docs/BENCHMARK.md"
fi
