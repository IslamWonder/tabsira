-- Refuse to replace the corpus when rows outside it point at it (docs/CORPUS.md).
--
-- Run by import.sh --force (and scripts/data.ps1 -Force) inside the import's
-- transaction, before the corpus tables are emptied. An editor's ruling, a learner's
-- state or a reviewed ontology candidate that names a corpus row would be lost or
-- refused by the emptying, so the import stops first and changes nothing. The
-- vectors are derived and go with the texts they were computed from.

DO $guard$
DECLARE
    r record;
    n bigint;
    found text := '';
BEGIN
    FOR r IN
        SELECT kn.nspname AS schema_name, k.relname AS table_name,
               (SELECT string_agg(format('%I IS NOT NULL', a.attname), ' AND ')
                FROM pg_attribute a
                WHERE a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)) AS points
        FROM pg_constraint c
        JOIN pg_class k ON k.oid = c.conrelid
        JOIN pg_namespace kn ON kn.oid = k.relnamespace
        JOIN pg_class f ON f.oid = c.confrelid
        JOIN pg_namespace fn ON fn.oid = f.relnamespace
        WHERE c.contype = 'f' AND fn.nspname = 'corpus' AND kn.nspname NOT IN ('corpus', 'vectors')
    LOOP
        EXECUTE format('SELECT count(*) FROM %I.%I WHERE %s', r.schema_name, r.table_name, r.points)
        INTO n;
        IF n > 0 THEN
            found := found || format(' %s.%s (%s rows)', r.schema_name, r.table_name, n);
        END IF;
    END LOOP;
    IF found <> '' THEN
        RAISE EXCEPTION 'rows outside the corpus point at it:% -- replacing the corpus would lose them, so nothing was imported', found;
    END IF;
END
$guard$;
