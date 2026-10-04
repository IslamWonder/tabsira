-- The CI database server, part 2 of 3: schemas and extensions.
--
-- Run once in each of tabsira, tabsira_test and tabsira_template, as the
-- postgres superuser (the role tabsira cannot create PostGIS, pgvector or
-- TimescaleDB). DECISIONS.md, decision 15: all nine are created here, so a
-- migration only ever finds them present and never silently skips one.
\set ON_ERROR_STOP on

SET search_path = public;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION tabsira;
CREATE SCHEMA IF NOT EXISTS geodata AUTHORIZATION tabsira;
CREATE SCHEMA IF NOT EXISTS vectors AUTHORIZATION tabsira;

CREATE EXTENSION IF NOT EXISTS postgis SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public;
CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA public;
CREATE EXTENSION IF NOT EXISTS btree_gin SCHEMA public;
CREATE EXTENSION IF NOT EXISTS btree_gist SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements SCHEMA public;
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
CREATE EXTENSION IF NOT EXISTS timescaledb SCHEMA public;
