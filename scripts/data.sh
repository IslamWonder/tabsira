#!/usr/bin/env bash
# Import the corpora (make data). Run `make migrate` first.
#
# The scripture store, in this order, every step idempotent:
#   download     quranpedia's current dump and the nine hadith files, each
#                checked against its SHA-256 (cached in data/cache/)
#   quran        quranpedia mushaf 2 into app.quran_verses, with history on corrections
#   annotations  data/corpus/quran-annotations.json, for retrieval only
#   hadith       the nine books into app.hadiths
#   signals      data/corpus/sunnah-enriched.json, repaired from cp720 and linked
#
# Then the vectors of every new or changed text for semantic search
# (src.cli.embed_corpus, the active provider's embedding model).
#
# The two files in data/corpus/ are the project's own corpora, too large for
# git; docs/ASSET_MANIFEST.md names them and their SHA-256. Then the world
# ontology and the learning path (scripts/data-learning.sh).
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CORPUS_DIR="$REPO_ROOT/data/corpus"
CORPUS_FILES="quran-annotations.json sunnah-enriched.json"

load_env
[[ -n "${DATABASE_URL:-}" ]] || die "DATABASE_URL is not set. Run scripts/setup-db.sh, then make migrate."
require_cmd uv "See https://docs.astral.sh/uv/"

for name in $CORPUS_FILES; do
	[[ -f "$CORPUS_DIR/$name" ]] ||
		die "$CORPUS_DIR/$name is missing. Copy it there (docs/ASSET_MANIFEST.md names its source and SHA-256)."
done

banner "Scripture store"
started=$SECONDS
(cd "$REPO_ROOT/apps/api" && uv run --quiet python -m src.cli.import_scripture \
	download quran annotations hadith signals --cache-dir "$REPO_ROOT/data/cache" --corpus-dir "$CORPUS_DIR")
ok "Scripture store imported in $((SECONDS - started)) s"

# Vectors for semantic search, with the active provider's embedding model. Only
# new or changed documents are sent, so a second run costs nothing; without an
# API key the step says so and is skipped (search then uses its lexical half).
banner "Scripture vectors"
started=$SECONDS
# The published archive first (docs/EMBEDDINGS.md), so embed_corpus finds nothing to compute.
bash "$REPO_ROOT/scripts/vectors/ensure.sh"
(cd "$REPO_ROOT/apps/api" && uv run --quiet python -m src.cli.embed_corpus)
ok "Scripture vectors checked in $((SECONDS - started)) s"

# shellcheck source=data-learning.sh
source "$(dirname "${BASH_SOURCE[0]}")/data-learning.sh"
banner "World ontology and learning path"
import_ontology
import_masar
