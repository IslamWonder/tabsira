-- Before the rows of a GeoNames dump are restored (scripts/geodata/ensure.sh and
-- scripts/data.ps1): one transaction that empties the geodata tables and drops their
-- plain indexes, remembered in a temporary table, so the load does not update them
-- row by row. The geodata chain's alembic_version is never touched. restore-end.sql
-- builds the indexes again and commits; a failure in between leaves the old rows.

BEGIN;
SET LOCAL search_path = '';
SET LOCAL maintenance_work_mem = '512MB';
CREATE TEMP TABLE geodata_indexes ON COMMIT DROP AS
SELECT format('%I.%I', n.nspname, ic.relname) AS name, pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index i
JOIN pg_class ic ON ic.oid = i.indexrelid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'geodata' AND t.relname <> 'alembic_version'
  AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid);
TRUNCATE geodata.geonames_hierarchy, geodata.geonames_alternate_names,
         geodata.geonames_country_info, geodata.geonames_postal_codes, geodata.geonames;
DO $drop$
DECLARE r record;
BEGIN
    FOR r IN SELECT name FROM pg_temp.geodata_indexes LOOP
        EXECUTE 'DROP INDEX ' || r.name;
    END LOOP;
END
$drop$;
