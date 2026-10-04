#!/usr/bin/env bash
# Make sure the reference data (the `corpus` schema: the scripture store, the world
# ontology and the learning path) is in the database, installed from the verified
# archive in the owners' bucket, never rebuilt from the third-party sources
# (docs/CORPUS.md, decision 57).
#
# Called by scripts/data.sh (make data) on a development machine and on the
# production host alike. It checks first and does nothing when the corpus is
# there: the 6,236 verses, hadiths, annotations, signals, the ontology and an
# active learning path mean the archive (or an import from the sources) was
# installed already.
#
# Otherwise it finds the archive, in this order:
#   CORPUS_ARCHIVE       a local tabsira-corpus-<date>.tar.gz (checked against the
#                        .sha256 beside it when there is one) or its extracted folder
#   CORPUS_ARCHIVE_URL   the archive in the owners' bucket (default: the address in
#                        docs/CORPUS.md); downloaded once into CORPUS_ARCHIVE_DIR
#                        (default ../tabsira-data/corpus beside the checkout) and
#                        checked against its .sha256
# then runs scripts/corpus/import.sh on it. With neither it stops with an error:
# scripts/data.sh only calls it when one of the two is set.
#
# Usage: scripts/corpus/ensure.sh [--force]
#   --force   import even when the corpus is there (also DATA_FORCE=true, from make data)
# The database and the keys above are read from the environment first, then from
# the root .env.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib.sh
source "$REPO_ROOT/scripts/lib.sh"

FORCE="${DATA_FORCE:-false}"
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=true ;;
	*) die "unknown argument: $arg (only --force)" ;;
	esac
done

load_env_keeping DATABASE_URL SYNC_DATABASE_URL CORPUS_ARCHIVE CORPUS_ARCHIVE_URL CORPUS_ARCHIVE_DIR
url="${SYNC_DATABASE_URL:-${DATABASE_URL:-}}"
[[ -n "$url" ]] || die "DATABASE_URL is not set. Run scripts/setup-db.sh, then make migrate."
require_cmd psql "Install the PostgreSQL client."
require_cmd pg_restore "Install the PostgreSQL client."
require_cmd sha256sum "Install coreutils."

DEFAULT_URL="https://s3-v2.riastorage.com/tabsira/corpus/tabsira-corpus-2026-10-04.tar.gz"
CORPUS_ARCHIVE="${CORPUS_ARCHIVE:-}"
CORPUS_ARCHIVE_URL="${CORPUS_ARCHIVE_URL-$DEFAULT_URL}"
CORPUS_ARCHIVE_DIR="${CORPUS_ARCHIVE_DIR:-$REPO_ROOT/../tabsira-data/corpus}"

url="${url/postgresql+asyncpg:/postgresql:}"
url="${url/postgresql+psycopg:/postgresql:}"
query() { psql -X -q -tA -v ON_ERROR_STOP=1 "$url" -c "$1"; }

[[ "$(query "SELECT to_regclass('corpus.quran_verses') IS NOT NULL")" == "t" ]] ||
	die "corpus.quran_verses is missing: run make migrate first."

installed="$(query "SELECT (SELECT count(*) FROM corpus.quran_verses) = 6236
	AND EXISTS (SELECT 1 FROM corpus.hadiths)
	AND EXISTS (SELECT 1 FROM corpus.quran_annotations)
	AND EXISTS (SELECT 1 FROM corpus.hadith_signals)
	AND EXISTS (SELECT 1 FROM corpus.ontology_entities)
	AND EXISTS (SELECT 1 FROM corpus.learning_path_versions WHERE is_active)")"
if [[ "$installed" == "t" && "$FORCE" != "true" ]]; then
	ok "The corpus (scripture, ontology, learning path) is already installed: nothing to do. Use --force to install it again."
	exit 0
fi

force_arg=()
[[ "$FORCE" == "true" ]] && force_arg=(--force)

if [[ -n "$CORPUS_ARCHIVE" ]]; then
	[[ -e "$CORPUS_ARCHIVE" ]] || die "CORPUS_ARCHIVE=$CORPUS_ARCHIVE does not exist."
	source_path="$CORPUS_ARCHIVE"
elif [[ -n "$CORPUS_ARCHIVE_URL" ]]; then
	require_cmd curl "Install curl."
	mkdir -p "$CORPUS_ARCHIVE_DIR"
	name="$(basename "$CORPUS_ARCHIVE_URL")"
	source_path="$CORPUS_ARCHIVE_DIR/$name"
	if [[ -f "$source_path" && -f "$source_path.sha256" ]] &&
		(cd "$CORPUS_ARCHIVE_DIR" && sha256sum --check --quiet "$name.sha256"); then
		log "Archive already downloaded and verified: $source_path"
	else
		log "Downloading the corpus (about 50 MB) from $CORPUS_ARCHIVE_URL ..."
		curl -fL --retry 3 -o "$source_path.sha256" "$CORPUS_ARCHIVE_URL.sha256"
		curl -fL --retry 3 -o "$source_path" "$CORPUS_ARCHIVE_URL"
		(cd "$CORPUS_ARCHIVE_DIR" && sha256sum --check --quiet "$name.sha256") ||
			die "$source_path does not match its .sha256: delete it and run again."
		ok "Archive verified against its .sha256"
	fi
else
	die "No corpus archive (CORPUS_ARCHIVE and CORPUS_ARCHIVE_URL are empty)."
fi

# The repository's import, never the archive's own copy (it may be older than the schema).
DATABASE_URL="$url" bash "$SCRIPT_DIR/import.sh" "${force_arg[@]+"${force_arg[@]}"}" "$source_path"
