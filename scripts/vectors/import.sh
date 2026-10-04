#!/usr/bin/env bash
# Import TABSIRA's scripture embeddings from this archive instead of recomputing them.
#
# The target database must already hold the scripture store (make data) and the
# vectors schema (make migrate runs its chain: vectors.quran_verse_embeddings and
# vectors.hadith_embeddings, decision 48). Each vector is matched to its verse by (surah, ayah) and
# to its hadith by (collection, number), and is imported only when the stored
# text's SHA-256 equals the one it was computed from; anything else is skipped and
# counted, never forced. Rows that already exist are left as they are.
#
# Usage, from the extracted folder, or from anywhere with that folder as argument
# (scripts/vectors/import.sh in the repository imports an archive whose own copy
# is older):
#   DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tabsira ./import.sh
#   DATABASE_URL=... scripts/vectors/import.sh ../tabsira-data/vectors/tabsira-vectors-2026-10-04
#   (or set PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE instead of DATABASE_URL)
set -euo pipefail
# The SQL lives beside this script (scripts/vectors/import.sql, or the archive's copy),
# shared with scripts/data.ps1; it reads the .tsv files of the current directory.
SQL_FILE="$(cd "$(dirname "$0")" && pwd)/import.sql"
cd "${1:-$(dirname "$0")}"

say() { printf '[vectors] %s\n' "$*"; }
die() {
	printf '[vectors] error: %s\n' "$*" >&2
	exit 1
}

command -v psql >/dev/null || die "psql is required"
command -v sha256sum >/dev/null || die "sha256sum is required"

# psql understands postgresql:// but not SQLAlchemy's postgresql+driver:// form.
url="${DATABASE_URL:-}"
url="${url/postgresql+asyncpg:/postgresql:}"
url="${url/postgresql+psycopg:/postgresql:}"
PSQL=(psql -X -v ON_ERROR_STOP=1 -q)
[[ -n "$url" ]] && PSQL+=("$url")

[[ -f "$SQL_FILE" ]] || die "$SQL_FILE is missing: run the import.sh of the repository"
[[ -f SHA256SUMS && -f quran_verse_embeddings.tsv && -f hadith_embeddings.tsv ]] ||
	die "$(pwd) is not an extracted vector archive"

say "checking the files against the manifest"
sha256sum --check --quiet SHA256SUMS || die "a file does not match SHA256SUMS; download the archive again"

for table in vectors.quran_verse_embeddings vectors.hadith_embeddings corpus.quran_verses corpus.hadiths; do
	found="$("${PSQL[@]}" -tA -c "SELECT to_regclass('$table') IS NOT NULL")"
	[[ "$found" == "t" ]] || die "$table is missing: run make migrate and make data first"
done

say "importing (this takes a few minutes: the vector indexes are built as rows arrive)"
"${PSQL[@]}" -f "$SQL_FILE"
say "done. Rows that already existed were kept; a row whose text changed must be recomputed by the embedding step."
