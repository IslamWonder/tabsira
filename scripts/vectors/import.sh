#!/usr/bin/env bash
# Import TABSIRA's scripture embeddings from this archive instead of recomputing them.
#
# The target database must already hold the scripture store (make data) and the
# retrieval tables (the app migration that creates app.quran_verse_embeddings and
# app.hadith_embeddings). Each vector is matched to its verse by (surah, ayah) and
# to its hadith by (collection, number), and is imported only when the stored
# text's SHA-256 equals the one it was computed from; anything else is skipped and
# counted, never forced. Rows that already exist are left as they are.
#
# Usage, from the extracted folder:
#   DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tabsira ./import.sh
#   (or set PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE and run ./import.sh)
set -euo pipefail
cd "$(dirname "$0")"

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

say "checking the files against the manifest"
sha256sum --check --quiet SHA256SUMS || die "a file does not match SHA256SUMS; download the archive again"

for table in quran_verse_embeddings hadith_embeddings quran_verses hadiths; do
	found="$("${PSQL[@]}" -tA -c "SELECT to_regclass('app.$table') IS NOT NULL")"
	[[ "$found" == "t" ]] || die "app.$table is missing: run the migrations and make data first"
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
    INSERT INTO app.quran_verse_embeddings (verse_id, model, dimensions, document_sha256, embedding)
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
    INSERT INTO app.hadith_embeddings (hadith_id, model, dimensions, document_sha256, embedding)
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
ANALYZE app.quran_verse_embeddings;
ANALYZE app.hadith_embeddings;
SQL
say "done. Rows that already existed were kept; a row whose text changed must be recomputed by the embedding step."
