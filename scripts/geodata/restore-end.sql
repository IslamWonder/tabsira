-- After the rows of a GeoNames dump are restored: build the indexes restore-begin.sql
-- dropped, from their saved definitions, and commit.

DO $build$
DECLARE r record;
BEGIN
    FOR r IN SELECT definition FROM pg_temp.geodata_indexes LOOP
        EXECUTE r.definition;
    END LOOP;
END
$build$;
COMMIT;
