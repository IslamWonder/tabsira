#!/usr/bin/env bash
# Make sure the scripture vectors are in the database without computing them.
#
# Called by scripts/data.sh (make data) on a development machine and on the
# production host alike, before embed_corpus, so that step finds nothing to send
# (docs/EMBEDDINGS.md). It checks first and does nothing when the vectors are
# there: a full store (every verse and every hadith) for one of the default
# embedding models means the archive was imported already.
#
# Otherwise it finds the archive, in this order:
#   VECTORS_ARCHIVE       a local tabsira-vectors-<date>.tar.gz, or its extracted folder
#   VECTORS_ARCHIVE_URL   the archive in the owners' bucket (default: the public address
#                         in docs/EMBEDDINGS.md); downloaded once into VECTORS_DIR
#                         (default ../tabsira-data/vectors beside the checkout) and
#                         checked against its .sha256; empty means "never download"
# then runs scripts/vectors/import.sh on the extracted folder. Without any archive
# it only warns: embed_corpus then computes the vectors, which costs money.
#
# Usage: scripts/vectors/ensure.sh [--force]   (reads the root .env)
#   --force   import even when the vectors are there (also DATA_FORCE=true, from make data)
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib.sh
source "$REPO_ROOT/scripts/lib.sh"

FORCE="${DATA_FORCE:-false}"
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=true ;;
	*) die "unknown argument: $arg" ;;
	esac
done

load_env
[[ -n "${DATABASE_URL:-}" ]] || die "DATABASE_URL is not set. Run scripts/setup-db.sh, then make migrate."
require_cmd psql "Install the PostgreSQL client."

DEFAULT_URL="https://s3-v2.riastorage.com/tabsira/vectors/tabsira-vectors-2026-10-04.tar.gz"
VECTORS_ARCHIVE="${VECTORS_ARCHIVE:-}"
VECTORS_ARCHIVE_URL="${VECTORS_ARCHIVE_URL-$DEFAULT_URL}"
VECTORS_DIR="${VECTORS_DIR:-$REPO_ROOT/../tabsira-data/vectors}"
# The models a fresh install searches with (docs/BENCHMARK.md): either one covering
# the whole store means the archive is in.
DEFAULT_MODELS="'text-embedding-3-large', 'bge-m3'"

url="${DATABASE_URL/postgresql+asyncpg:/postgresql:}"
url="${url/postgresql+psycopg:/postgresql:}"
query() { psql -X -q -tA -v ON_ERROR_STOP=1 "$url" -c "$1"; }

for table in vectors.quran_verse_embeddings vectors.hadith_embeddings corpus.quran_verses corpus.hadiths; do
	[[ "$(query "SELECT to_regclass('$table') IS NOT NULL")" == "t" ]] ||
		die "$table is missing: run make migrate, then the scripture store import (make data)."
done

covered="$(query "
	SELECT count(*) FROM (
		SELECT model FROM vectors.quran_verse_embeddings
		WHERE model IN ($DEFAULT_MODELS) GROUP BY model
		HAVING count(*) >= (SELECT count(*) FROM corpus.quran_verses)
		INTERSECT
		SELECT model FROM vectors.hadith_embeddings
		WHERE model IN ($DEFAULT_MODELS) GROUP BY model
		HAVING count(*) >= (SELECT count(*) FROM corpus.hadiths)
	) full_models")"
if [[ "$covered" != "0" && "$FORCE" != "true" ]]; then
	ok "Scripture vectors are already in the database: nothing to import. Use --force to import again."
	exit 0
fi

folder=""
archive=""
if [[ -n "$VECTORS_ARCHIVE" ]]; then
	if [[ -d "$VECTORS_ARCHIVE" ]]; then
		folder="$VECTORS_ARCHIVE"
	elif [[ -f "$VECTORS_ARCHIVE" ]]; then
		archive="$VECTORS_ARCHIVE"
	else
		die "VECTORS_ARCHIVE=$VECTORS_ARCHIVE is neither an archive nor an extracted folder."
	fi
elif [[ -n "$VECTORS_ARCHIVE_URL" ]]; then
	require_cmd curl "Install curl."
	require_cmd sha256sum "Install coreutils."
	mkdir -p "$VECTORS_DIR"
	archive="$VECTORS_DIR/$(basename "$VECTORS_ARCHIVE_URL")"
	if [[ -f "$archive" && -f "$archive.sha256" ]] && (cd "$VECTORS_DIR" && sha256sum --check --quiet "$(basename "$archive").sha256"); then
		log "Archive already downloaded and verified: $archive"
	else
		log "Downloading the scripture vectors (about 930 MB) from $VECTORS_ARCHIVE_URL ..."
		curl -fL --retry 3 -o "$archive.sha256" "$VECTORS_ARCHIVE_URL.sha256"
		curl -fL --retry 3 -C - -o "$archive" "$VECTORS_ARCHIVE_URL"
		(cd "$VECTORS_DIR" && sha256sum --check --quiet "$(basename "$archive").sha256") ||
			die "$archive does not match its .sha256: delete it and run again."
		ok "Archive verified against its .sha256"
	fi
else
	warn "No vector archive (VECTORS_ARCHIVE empty, VECTORS_ARCHIVE_URL empty): embed_corpus will compute the vectors, which costs money."
	exit 0
fi

if [[ -z "$folder" ]]; then
	require_cmd tar "Install tar."
	name="$(basename "$archive" .tar.gz)"
	folder="$(dirname "$archive")/$name"
	if [[ ! -f "$folder/SHA256SUMS" ]]; then
		log "Extracting $archive ..."
		tar -xzf "$archive" -C "$(dirname "$archive")"
	fi
fi
[[ -f "$folder/SHA256SUMS" ]] || die "$folder is not an extracted vector archive."

# The repository's import, never the archive's own copy (it may predate the vectors schema).
DATABASE_URL="$url" bash "$SCRIPT_DIR/import.sh" "$folder"
