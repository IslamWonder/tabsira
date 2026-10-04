"""The test database, as built from the models: what the other tests stand on."""

from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import func, inspect, select, text

from src.models import Base, GeoBase, GeoName

EXTENSIONS = {
    "postgis",
    "pg_trgm",
    "unaccent",
    "pgcrypto",
    "btree_gin",
    "btree_gist",
    "pg_stat_statements",
    "vector",
    "timescaledb",
}


async def test_both_schemas_and_every_extension_exist(engine, db_session):
    schemas = set((await db_session.execute(text("SELECT nspname FROM pg_namespace"))).scalars())
    extensions = set((await db_session.execute(text("SELECT extname FROM pg_extension"))).scalars())
    homes = set(
        (
            await db_session.execute(
                text(
                    "SELECT DISTINCT n.nspname FROM pg_extension e "
                    "JOIN pg_namespace n ON n.oid = e.extnamespace "
                    "WHERE e.extname IN ('postgis', 'pg_trgm', 'vector')"
                )
            )
        ).scalars()
    )

    assert {"app", "geodata"} <= schemas
    assert extensions >= EXTENSIONS
    # Extension objects live in public, never in the application schemas.
    assert homes == {"public"}


async def test_the_geonames_tables_and_their_indexes_are_built(engine):
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: set(inspect(c).get_table_names("geodata")))
        indexes = await connection.run_sync(
            lambda c: {i["name"] for i in inspect(c).get_indexes("geonames", "geodata")}
        )

    assert tables == {table.name for table in GeoBase.metadata.tables.values()}
    assert {
        "ix_geonames_name_trgm",
        "ix_geonames_location_geom",
        "ix_geonames_country_admin1",
        "ix_geonames_population",
    } <= indexes


async def test_the_app_schema_matches_its_models(engine):
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: set(inspect(c).get_table_names("app")))

    assert tables == {table.name for table in Base.metadata.tables.values()}


async def test_a_geoname_keeps_its_point_and_is_found_by_distance_and_by_similar_name(db_session):
    tunis = GeoName(
        geoname_id=2464915,
        name="Tunis",
        latitude=36.81897,
        longitude=10.16579,
        location_geom=func.ST_SetSRID(func.ST_MakePoint(10.16579, 36.81897), 4326),
    )
    db_session.add(tunis)
    await db_session.flush()

    longitude = await db_session.scalar(select(func.ST_X(GeoName.location_geom)))
    near = await db_session.scalar(
        select(GeoName.name).where(
            func.ST_DWithin(
                GeoName.location_geom.cast(Geography),
                func.ST_SetSRID(func.ST_MakePoint(10.2, 36.8), 4326).cast(Geography),
                10_000,
            )
        )
    )
    similar = await db_session.scalar(select(GeoName.name).where(GeoName.name.op("%")("Tunes")))

    assert longitude == 10.16579
    assert near == "Tunis"
    assert similar == "Tunis"
