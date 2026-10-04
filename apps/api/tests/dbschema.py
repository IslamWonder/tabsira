"""Build the test schema on an open connection; shared by conftest and the migration tests."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from src.models import Base, GeoBase, VectorsBase

# The database-side extensions the schema relies on; the app chain's first
# migration creates the same list.
EXTENSIONS = (
    "postgis",
    "pg_trgm",
    "unaccent",
    "pgcrypto",
    "btree_gin",
    "btree_gist",
    "pg_stat_statements",
    "vector",
    "timescaledb",
)
SCHEMAS = ("app", "geodata", "vectors")


async def reset_schemas(connection: AsyncConnection) -> None:
    """Drop every table, function and enum type in the three schemas, whatever created them."""
    await connection.execute(
        text(
            """
            DO $$
            DECLARE r record;
            BEGIN
                FOR r IN SELECT schemaname, tablename FROM pg_tables
                         WHERE schemaname IN ('app', 'geodata', 'vectors') LOOP
                    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', r.schemaname, r.tablename);
                END LOOP;
                FOR r IN SELECT n.nspname, p.proname, p.oid FROM pg_proc p
                         JOIN pg_namespace n ON n.oid = p.pronamespace
                         WHERE n.nspname IN ('app', 'geodata', 'vectors') LOOP
                    EXECUTE format('DROP FUNCTION IF EXISTS %I.%I CASCADE', r.nspname, r.proname);
                END LOOP;
                FOR r IN SELECT n.nspname, t.typname FROM pg_type t
                         JOIN pg_namespace n ON n.oid = t.typnamespace
                         WHERE n.nspname IN ('app', 'geodata', 'vectors') AND t.typtype = 'e' LOOP
                    EXECUTE format('DROP TYPE IF EXISTS %I.%I CASCADE', r.nspname, r.typname);
                END LOOP;
            END $$;
            """
        )
    )


async def create_schema(connection: AsyncConnection) -> None:
    """
    Build the whole test schema on an open connection.

    One definition, used by the plain run and by the xdist template, so the two
    can never disagree about what the schema is. An extension that is not
    installed makes this fail, loudly: the test database is provisioned by
    scripts/setup-db.sh and the suite does not pretend otherwise.
    """
    for extension in EXTENSIONS:
        await connection.execute(
            text(f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public')
        )
    for schema in SCHEMAS:
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    await reset_schemas(connection)
    await connection.run_sync(GeoBase.metadata.create_all)
    await connection.run_sync(Base.metadata.create_all)
    await connection.run_sync(VectorsBase.metadata.create_all)
