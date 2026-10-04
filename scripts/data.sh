#!/usr/bin/env bash
# Import the corpora (make data). Run `make migrate` first.
#
# Usage: scripts/data.sh [--force]
#   CORPUS_DIR=<folder>  where the two corpus files are (default data/corpus of the checkout)
#   Data already there (the scripture store, the vectors) is left alone; --force,
#   or DATA_FORCE=true with make data, imports it again. GeoNames has the same
#   guard in scripts/seed-geonames.sh.
#
# The scripture store, in this order, every step idempotent:
#   download     quranpedia's current dump and the nine hadith files, each
#                checked against its SHA-256 (cached in data/cache/)
#   quran        quranpedia mushaf 2 into corpus.quran_verses, with history on corrections
#   annotations  data/corpus/quran-annotations.json, for retrieval only
#   hadith       the nine books into corpus.hadiths
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

CORPUS_DIR="${CORPUS_DIR:-$REPO_ROOT/data/corpus}"
CORPUS_FILES="quran-annotations.json sunnah-enriched.json"

# Data that is there is left alone; --force (or DATA_FORCE=true) imports it again.
FORCE="${DATA_FORCE:-false}"
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=true ;;
	*) die "unknown argument: $arg (only --force)" ;;
	esac
done
export DATA_FORCE="$FORCE"

load_env
# In a production release the Python environment is built without development dependencies; `uv run` must not add them.
[[ "${ENVIRONMENT:-}" != "production" ]] || export UV_NO_SYNC=1
[[ -n "${DATABASE_URL:-}" ]] || die "DATABASE_URL is not set. Run scripts/setup-db.sh, then make migrate."
require_cmd uv "See https://docs.astral.sh/uv/"
require_cmd psql "Install the PostgreSQL client."
sync_url="${SYNC_DATABASE_URL:-$DATABASE_URL}"
sync_url="${sync_url/postgresql+asyncpg:/postgresql:}"
sync_url="${sync_url/postgresql+psycopg:/postgresql:}"
query() { psql -X -q -tA -v ON_ERROR_STOP=1 "$sync_url" -c "$1"; }

for name in $CORPUS_FILES; do
	[[ -f "$CORPUS_DIR/$name" ]] ||
		die "$CORPUS_DIR/$name is missing. Copy it there, or set CORPUS_DIR to the folder that holds it (docs/ASSET_MANIFEST.md names its source and SHA-256)."
done

banner "Scripture store"
started=$SECONDS
# The whole Quran, hadiths, annotations and signals already stored mean the store was imported.
stored="$(query "SELECT (SELECT count(*) FROM corpus.quran_verses) = 6236
	AND (SELECT count(*) FROM corpus.hadiths) > 0
	AND (SELECT count(*) FROM corpus.quran_annotations) > 0
	AND (SELECT count(*) FROM corpus.hadith_signals) > 0" 2>/dev/null || echo f)"
if [[ "$stored" == "t" && "$FORCE" != "true" ]]; then
	ok "Scripture store already imported: nothing to do. Use --force to import again."
else
	(cd "$REPO_ROOT/apps/api" && uv run --quiet python -m src.cli.import_scripture \
		download quran annotations hadith signals --cache-dir "$REPO_ROOT/data/cache" --corpus-dir "$CORPUS_DIR")
	ok "Scripture store imported in $((SECONDS - started)) s"
fi

# The ontology and the learning path ship in the repository and load in seconds:
# before the vectors, so a download or an API key problem there never leaves a
# server without them.
# shellcheck source=data-learning.sh
source "$(dirname "${BASH_SOURCE[0]}")/data-learning.sh"
banner "World ontology and learning path"
import_ontology
import_masar

# Vectors for semantic search, with the active provider's embedding model. Only
# new or changed documents are sent, so a second run costs nothing; without an
# API key the step says so and is skipped (search then uses its lexical half).
banner "Scripture vectors"
started=$SECONDS
# The published archive first (docs/EMBEDDINGS.md), so embed_corpus finds nothing to compute.
bash "$REPO_ROOT/scripts/vectors/ensure.sh"
(cd "$REPO_ROOT/apps/api" && uv run --quiet python -m src.cli.embed_corpus)
ok "Scripture vectors checked in $((SECONDS - started)) s"
