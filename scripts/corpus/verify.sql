-- Check a restored corpus before the import commits (docs/CORPUS.md).
--
-- Run by import.sh (and scripts/data.ps1) inside the import's transaction, after the
-- rows are restored, with the archive's manifest in the setting
-- tabsira.corpus_manifest. Every verse, past verse and hadith must match the
-- SHA-256 of its UTF-8 bytes (the hash src/scripture/text.py computes), and every
-- table must match the manifest's count and fingerprints (state.sql). Any
-- difference raises, and the transaction, so the import, is rolled back. Then the
-- verse spans of the leak guard are rebuilt from the restored rows.

\ir state.sql
DO $check$
DECLARE
    expected jsonb := current_setting('tabsira.corpus_manifest')::jsonb -> 'tables';
    found jsonb := pg_temp.corpus_state();
    bad bigint;
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['quran_verses', 'quran_verse_history', 'hadiths'] LOOP
        EXECUTE format(
            'SELECT count(*) FROM corpus.%I '
            'WHERE text_sha256 IS DISTINCT FROM encode(sha256(convert_to(text, ''UTF8'')), ''hex'')', t)
        INTO bad;
        IF bad > 0 THEN
            RAISE EXCEPTION 'corpus.%: % rows whose text does not match its stored hash; nothing was imported', t, bad;
        END IF;
    END LOOP;
    FOR t IN SELECT jsonb_object_keys(expected) LOOP
        IF found -> t IS DISTINCT FROM expected -> t THEN
            RAISE EXCEPTION 'corpus.% does not match the manifest (expected %, found %); nothing was imported',
                t, expected -> t, found -> t;
        END IF;
    END LOOP;
END
$check$;
REFRESH MATERIALIZED VIEW corpus.quran_verse_spans;
