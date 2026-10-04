#!/usr/bin/env bash
# Evaluate the insight engine on the gold scenes and the chat cases (make eval):
# every image of apps/api/tests/evaluation/scenes/ goes through the whole scan pipeline with
# the active provider, and the result is checked by rule (no scripture leaked,
# every reference resolves to a hash-checked stored text, abstention where the
# scene calls for it, time per stage, cost per scan). The report is written to
# docs/EVALUATION.md, the raw results to apps/api/tests/evaluation/results/
# (not committed).
#
# It calls the real providers with the keys of the root .env and costs money
# (about three cents a scene; --max-cost caps it, default 2 dollars). Run
# `make migrate && make data` first; services/vision (detector and reranker)
# should run, and without it the scenes are analysed without boxes and the
# evidence is kept in its fused order, which the report says.
#
# Then the twelve chat cases (v2 §27.16, apps/api/tests/evaluation/chat/cases.json)
# are asked through the chat service in transactions that are rolled back, and
# written to their own section of docs/EVALUATION.md.
#
# Usage: scripts/eval.sh [--only scenes|chat] [--scenes a,b] [--cases a,b]
#                        [--max-cost USD] [--no-report]
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

have uv || die "uv is not installed. Run: make install"
cd "$REPO_ROOT/apps/api"
uv run python -m src.cli.evaluate "$@"

# The report is generated; format it the way the checks want it.
if have pnpm && [[ -d "$REPO_ROOT/node_modules" ]]; then
	cd "$REPO_ROOT"
	pnpm exec prettier --log-level warn --write docs/EVALUATION.md
else
	warn "pnpm is missing: run 'make format' before committing docs/EVALUATION.md"
fi
