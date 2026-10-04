-- Import the scripture vectors of an extracted archive (scripts/vectors/import.sh and
-- scripts/data.ps1), run from the archive's folder: it reads its two .tsv files.
-- A vector is inserted only when its text is in the store with the same SHA-256;
-- the others are counted and skipped, and existing rows are kept.

BEGIN;
CREATE TEMP TABLE staged_verses (surah int, ayah int, text_sha256 text, model text, dimensions smallint, document_sha256 text, embedding text) ON COMMIT DROP;
CREATE TEMP TABLE staged_hadiths (collection text, number text, text_sha256 text, model text, dimensions smallint, document_sha256 text, embedding text) ON COMMIT DROP;
\copy staged_verses FROM 'quran_verse_embeddings.tsv' WITH (FORMAT text)
\copy staged_hadiths FROM 'hadith_embeddings.tsv' WITH (FORMAT text)

CREATE TEMP TABLE report (corpus text, model text, dimensions smallint, staged bigint, inserted bigint, text_changed bigint, not_in_store bigint) ON COMMIT DROP;

WITH matched AS (
    SELECT s.*, v.id AS verse_id, v.text_sha256 AS current_sha
    FROM staged_verses s LEFT JOIN corpus.quran_verses v ON v.surah = s.surah AND v.ayah = s.ayah
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
    FROM staged_hadiths s LEFT JOIN corpus.hadiths h ON h.collection = s.collection AND h.number = s.number
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
