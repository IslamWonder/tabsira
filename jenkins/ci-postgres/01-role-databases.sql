-- The CI database server, part 1 of 3: the role and the three databases.
--
-- The SQL equivalent of scripts/setup-db.sh for a throwaway server, run by
-- jenkins/ci-services.sh as the postgres superuser. Keep the two in step: the
-- role, the three databases and the search_path must read the same in both.
--
-- Expects the psql variable app_password, set by ci-services.sh over stdin so
-- the password never sits on a command line.
--
--   role      tabsira  login, not a superuser, CREATEDB (pytest-xdist copies a
--             template per worker), search_path app, corpus, geodata, vectors, public
--   databases tabsira           the database the migrations run against
--             tabsira_test      the API test suite
--             tabsira_template  an empty copy of the setup, closed to connections
\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tabsira') THEN
    CREATE ROLE tabsira LOGIN;
  END IF;
END
$$;

ALTER ROLE tabsira WITH LOGIN CREATEDB PASSWORD :'app_password';
ALTER ROLE tabsira SET search_path = app, corpus, geodata, vectors, public;
-- CI only: each test worker ends with DROP DATABASE ... WITH (FORCE) on its copy,
-- which must also end a session that is not the role's own (an autovacuum or
-- extension worker that joined meanwhile); without this the drop fails at random.
GRANT pg_signal_backend TO tabsira;

CREATE DATABASE tabsira OWNER tabsira ENCODING 'UTF8' TEMPLATE template0;
CREATE DATABASE tabsira_test OWNER tabsira ENCODING 'UTF8' TEMPLATE template0;
CREATE DATABASE tabsira_template OWNER tabsira ENCODING 'UTF8' TEMPLATE template0;
