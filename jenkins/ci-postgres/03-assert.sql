-- The CI database server, part 3 of 3: refuse an image that lacks something.
--
-- Run in each of the three databases. A bad image fails here, with the names of
-- what is missing, instead of as a migration error twenty minutes into a build.
-- The NOTICE puts the versions in every build log, which is the cheap way to
-- notice the CI image drifting away from what production runs.
\set ON_ERROR_STOP on

DO $$
DECLARE
  missing text;
BEGIN
  SELECT string_agg(e, ', ' ORDER BY e)
  INTO missing
  FROM unnest(ARRAY[
    'postgis', 'pg_trgm', 'unaccent', 'pgcrypto', 'btree_gin', 'btree_gist',
    'pg_stat_statements', 'vector', 'timescaledb'
  ]) AS e
  WHERE NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = e);

  IF missing IS NOT NULL THEN
    RAISE EXCEPTION 'the CI database image is missing extensions: %', missing;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'app')
     OR NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'geodata') THEN
    RAISE EXCEPTION 'the schemas app and geodata are not both present in %', current_database();
  END IF;

  RAISE NOTICE '% ready: postgres %, postgis %, vector %, timescaledb %',
    current_database(),
    current_setting('server_version'),
    (SELECT extversion FROM pg_extension WHERE extname = 'postgis'),
    (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
    (SELECT extversion FROM pg_extension WHERE extname = 'timescaledb');
END
$$;
