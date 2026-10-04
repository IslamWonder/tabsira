#!/usr/bin/env bash
# Install the reference data (make data). Run `make migrate` first.
#
# Usage: scripts/data.sh [--force] [--geonames | --no-geonames] [--geonames-source=dump|geonames]
#
# In this order, each step once only (it skips what is there; --force, or
# DATA_FORCE=true with make data, installs everything again):
#
#   GeoNames   scripts/geodata/ensure.sh: the verified dump from the owners' bucket
#              (GEONAMES_SOURCE=dump, the default) or a fresh import from geonames.org
#              (geonames). On a development machine only when GEODATA_DUMP or
#              GEODATA_DUMP_URL is set, GEONAMES_SOURCE is geonames, or --geonames
#              is given; --no-geonames skips it always. deploy/load-data.sh asks
#              for it by default.
#   corpus     the `corpus` schema: the scripture store, the world ontology and the
#              learning path (decision 57, docs/CORPUS.md). From the verified archive
#              (scripts/corpus/ensure.sh) when CORPUS_ARCHIVE or CORPUS_ARCHIVE_URL
#              is set, the default. With both empty, built from the sources as
#              before: quranpedia's dump and the nine hadith files (checked against
#              their SHA-256, cached in data/cache/), the two corpus files of
#              CORPUS_DIR (default data/corpus; docs/ASSET_MANIFEST.md names them),
#              then the ontology and the learning path from the repository
#              (scripts/data-learning.sh).
#   vectors    scripts/vectors/ensure.sh imports the published archive
#              (docs/EMBEDDINGS.md); src.cli.embed_corpus then computes only what
#              is missing, with the active provider's embedding model.
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

CORPUS_DIR="${CORPUS_DIR:-$REPO_ROOT/data/corpus}"
CORPUS_FILES="quran-annotations.json sunnah-enriched.json"

# Data that is there is left alone; --force (or DATA_FORCE=true) imports it again.
FORCE="${DATA_FORCE:-false}"
GEONAMES=""
GEONAMES_SOURCE_ARG=""
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=true ;;
	--geonames) GEONAMES=true ;;
	--no-geonames) GEONAMES=false ;;
	--geonames-source=*)
		GEONAMES_SOURCE_ARG="${arg#*=}"
		[[ -n "$GEONAMES" ]] || GEONAMES=true
		;;
	*) die "unknown argument: $arg (--force, --geonames, --no-geonames, --geonames-source=dump|geonames)" ;;
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

# ─── GeoNames ───────────────────────────────────────────────────────
if [[ -z "$GEONAMES" ]]; then
	if [[ -n "${GEODATA_DUMP:-}${GEODATA_DUMP_URL:-}" || "${GEONAMES_SOURCE:-dump}" == "geonames" ]]; then
		GEONAMES=true
	else
		GEONAMES=false
	fi
fi
if [[ "$GEONAMES" == "true" ]]; then
	banner "GeoNames"
	geonames_args=()
	[[ -n "$GEONAMES_SOURCE_ARG" ]] && geonames_args=("--geonames-source=$GEONAMES_SOURCE_ARG")
	bash "$REPO_ROOT/scripts/geodata/ensure.sh" "${geonames_args[@]+"${geonames_args[@]}"}"
else
	log "GeoNames skipped: set GEODATA_DUMP_URL (or GEONAMES_SOURCE=geonames), or pass --geonames, to install the places of the atlas."
fi

# ─── The corpus: scripture store, ontology, learning path ──────────
# An unset CORPUS_ARCHIVE_URL means the bucket's default; only an empty one means "never download".
if [[ -n "${CORPUS_ARCHIVE:-}" || "${CORPUS_ARCHIVE_URL-default}" != "" ]]; then
	banner "Corpus (scripture store, world ontology, learning path) from its archive"
	started=$SECONDS
	bash "$REPO_ROOT/scripts/corpus/ensure.sh"
	ok "Corpus checked in $((SECONDS - started)) s"
else
	warn "No corpus archive configured (CORPUS_ARCHIVE and CORPUS_ARCHIVE_URL empty): building the store from its sources."
	for name in $CORPUS_FILES; do
		[[ -f "$CORPUS_DIR/$name" ]] ||
			die "$CORPUS_DIR/$name is missing. Copy it there, or set CORPUS_DIR to the folder that holds it (docs/ASSET_MANIFEST.md names its source and SHA-256), or set CORPUS_ARCHIVE_URL."
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
fi

# Vectors for semantic search, with the active provider's embedding model. Only
# new or changed documents are sent, so a second run costs nothing; without an
# API key the step says so and is skipped (search then uses its lexical half).
banner "Scripture vectors"
started=$SECONDS
# The published archive first (docs/EMBEDDINGS.md), so embed_corpus finds nothing to compute.
bash "$REPO_ROOT/scripts/vectors/ensure.sh"
(cd "$REPO_ROOT/apps/api" && uv run --quiet python -m src.cli.embed_corpus)
ok "Scripture vectors checked in $((SECONDS - started)) s"
