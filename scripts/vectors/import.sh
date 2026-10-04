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

[[ -f SHA256SUMS && -f quran_verse_embeddings.tsv && -f hadith_embeddings.tsv ]] ||
	die "$(pwd) is not an extracted vector archive"

say "checking the files against the manifest"
sha256sum --check --quiet SHA256SUMS || die "a file does not match SHA256SUMS; download the archive again"

for table in vectors.quran_verse_embeddings vectors.hadith_embeddings app.quran_verses app.hadiths; do
	found="$("${PSQL[@]}" -tA -c "SELECT to_regclass('$table') IS NOT NULL")"
	[[ "$found" == "t" ]] || die "$table is missing: run make migrate and make data first"
done

say "importing (this takes a few minutes: the vector indexes are built as rows arrive)"
"${PSQL[@]}" <<'SQL'
BEGIN;
CREATE TEMP TABLE staged_verses (surah int, ayah int, text_sha256 text, model text, dimensions smallint, document_sha256 text, embedding text) ON COMMIT DROP;
CREATE TEMP TABLE staged_hadiths (collection text, number text, text_sha256 text, model text, dimensions smallint, document_sha256 text, embedding text) ON COMMIT DROP;
\copy staged_verses FROM 'quran_verse_embeddings.tsv' WITH (FORMAT text)
\copy staged_hadiths FROM 'hadith_embeddings.tsv' WITH (FORMAT text)

CREATE TEMP TABLE report (corpus text, model text, dimensions smallint, staged bigint, inserted bigint, text_changed bigint, not_in_store bigint) ON COMMIT DROP;

WITH matched AS (
    SELECT s.*, v.id AS verse_id, v.text_sha256 AS current_sha
    FROM staged_verses s LEFT JOIN app.quran_verses v ON v.surah = s.surah AND v.ayah = s.ayah
), inserted AS (
    INSERT INTO vectors.quran_verse_embeddings (verse_id, model, dimensions, document_sha256, embedding)
    SELECT verse_id, model, dimensions, document_sha256, embedding::vector
    FROM matched WHERE verse_id IS NOT NULL AND current_sha = text_sha256
    ON CONFLICT DO NOTHING
    RETURNING model, dimensions
)
INSERT INTO report
SELECT 'quran', m.model, m.dimensions, count(*),
       (SELECT count(*) FROM inserted i WHERE i.model = m.model AND i.dimensions = m.dimensions),
       count(*) FILTER (WHERE m.verse_id IS NOT NULL AND m.current_sha <> m.text_sha256),
       count(*) FILTER (WHERE m.verse_id IS NULL)
FROM matched m GROUP BY m.model, m.dimensions;

WITH matched AS (
    SELECT s.*, h.id AS hadith_id, h.text_sha256 AS current_sha
    FROM staged_hadiths s LEFT JOIN app.hadiths h ON h.collection = s.collection AND h.number = s.number
), inserted AS (
    INSERT INTO vectors.hadith_embeddings (hadith_id, model, dimensions, document_sha256, embedding)
    SELECT hadith_id, model, dimensions, document_sha256, embedding::vector
    FROM matched WHERE hadith_id IS NOT NULL AND current_sha = text_sha256
    ON CONFLICT DO NOTHING
    RETURNING model, dimensions
)
INSERT INTO report
SELECT 'hadith', m.model, m.dimensions, count(*),
       (SELECT count(*) FROM inserted i WHERE i.model = m.model AND i.dimensions = m.dimensions),
       count(*) FILTER (WHERE m.hadith_id IS NOT NULL AND m.current_sha <> m.text_sha256),
       count(*) FILTER (WHERE m.hadith_id IS NULL)
FROM matched m GROUP BY m.model, m.dimensions;

\echo
\echo 'corpus | model | dimensions | in archive | imported now | skipped: text changed | skipped: not in store'
SELECT corpus, model, dimensions, staged, inserted, text_changed, not_in_store FROM report ORDER BY corpus, model;
COMMIT;
ANALYZE vectors.quran_verse_embeddings;
ANALYZE vectors.hadith_embeddings;
SQL
say "done. Rows that already existed were kept; a row whose text changed must be recomputed by the embedding step."
