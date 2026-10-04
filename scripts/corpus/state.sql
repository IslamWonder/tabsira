-- What the `corpus` schema holds, as one JSON object (docs/CORPUS.md).
--
-- Shared by export.sh, which writes it into the archive's manifest, and import.sh,
-- which computes it again after the restore and refuses the import unless the two
-- agree. Copied into every archive with import.sh, so an archive verifies itself.
--
-- For every table of the schema: its row count and a fingerprint, the SHA-256 of
-- the SHA-256 of each row's text, in primary-key order. Tables that keep scripture
-- (a `text_sha256` column) also get a fingerprint of the stored text hashes alone.
-- The settings below make a row print the same on any server: UTC, ISO dates,
-- shortest exact floats, and keys ordered byte by byte (COLLATE "C").
--
-- Usage: psql -f state.sql, then SELECT pg_temp.corpus_state();
-- The function lives in the session's temporary schema and goes with it.

CREATE OR REPLACE FUNCTION pg_temp.corpus_state() RETURNS jsonb
LANGUAGE plpgsql AS $state$
DECLARE
    r record;
    result jsonb := '{}';
    row_count bigint;
    fingerprint text;
    text_fingerprint text;
BEGIN
    PERFORM set_config('TimeZone', 'UTC', true);
    PERFORM set_config('DateStyle', 'ISO, YMD', true);
    PERFORM set_config('IntervalStyle', 'postgres', true);
    PERFORM set_config('extra_float_digits', '1', true);
    FOR r IN
        SELECT c.relname,
               (SELECT string_agg(
                           format('(t.%I)::text COLLATE "C"', a.attname), ', '
                           ORDER BY array_position(i.indkey::int2[], a.attnum))
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
                WHERE i.indrelid = c.oid AND i.indisprimary) AS key_order,
               EXISTS (SELECT 1 FROM pg_attribute a
                       WHERE a.attrelid = c.oid AND a.attname = 'text_sha256'
                         AND NOT a.attisdropped) AS keeps_text
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'corpus' AND c.relkind = 'r'
        ORDER BY c.relname COLLATE "C"
    LOOP
        IF r.key_order IS NULL THEN
            RAISE EXCEPTION 'corpus.% has no primary key, so it has no stable order', r.relname;
        END IF;
        EXECUTE format(
            'SELECT count(*), encode(sha256(convert_to('
            'coalesce(string_agg(encode(sha256('
            'convert_to((t.*)::text, ''UTF8'')), ''hex''), '''' ORDER BY %s), ''''), '
            '''UTF8'')), ''hex'') FROM corpus.%I AS t',
            r.key_order, r.relname)
        INTO row_count, fingerprint;
        text_fingerprint := NULL;
        IF r.keeps_text THEN
            EXECUTE format(
                'SELECT encode(sha256(convert_to('
                'coalesce(string_agg(t.text_sha256, '''' ORDER BY %s), ''''), '
                '''UTF8'')), ''hex'') FROM corpus.%I AS t',
                r.key_order, r.relname)
            INTO text_fingerprint;
        END IF;
        result := result || jsonb_build_object(
            r.relname,
            jsonb_strip_nulls(jsonb_build_object(
                'rows', row_count,
                'fingerprint', fingerprint,
                'text_fingerprint', text_fingerprint)));
    END LOOP;
    RETURN result;
END
$state$;
