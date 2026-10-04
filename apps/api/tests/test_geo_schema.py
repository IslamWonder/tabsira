"""What the search columns and indexes of the geodata schema do, on the database built from the models."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.models import GeoAlternateName, GeoHierarchy, GeoName
from src.models.geonames import NORMALIZE_NAME_SQL

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION = next((API_DIR / "alembic_geodata" / "versions").glob("*_add_search_columns.py"))


async def normalized(session, value: str | None) -> str | None:
    return (
        await session.execute(text("SELECT geodata.normalize_name(:value)"), {"value": value})
    ).scalar_one()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Arabic: vowel marks and the elongation stroke go.
        ("مَكَّة المُكَرَّمَة", "مكه المكرمه"),
        ("تـونس", "تونس"),
        # The spellings people type interchangeably become one.
        ("الإسكندرية", "الاسكندريه"),
        ("الاسكندرية", "الاسكندريه"),
        ("آل", "ال"),
        ("القاهرة", "القاهره"),
        ("مؤتة", "موته"),
        ("ٱلله", "الله"),
        ("على", "علي"),
        # Latin: case, accents, punctuation and spacing.
        ("Tūnis", "tunis"),
        ("São Paulo", "sao paulo"),
        ("  Sidi  Bou Saïd ", "sidi bou said"),
        ("Hammam-Lif", "hammam lif"),
        ("N'Djamena", "n djamena"),
        ("Ar-Riyāḍ", "ar riyad"),
        ("", ""),
    ],
)
async def test_names_are_folded_for_searching(db_session, raw, expected):
    assert await normalized(db_session, raw) == expected


async def test_a_missing_name_stays_missing(db_session):
    assert await normalized(db_session, None) is None


async def test_the_folded_name_is_computed_by_the_database_on_every_write(db_session):
    db_session.add(GeoName(geoname_id=1, name="Tunis"))
    alternate = GeoAlternateName(
        alternate_name_id=1, geoname_id=1, iso_language="ar", alternate_name="تُونِس"
    )
    db_session.add(alternate)
    await db_session.flush()
    await db_session.refresh(alternate)

    assert alternate.name_norm == "تونس"

    alternate.alternate_name = "Tūnis"
    await db_session.flush()
    await db_session.refresh(alternate)

    assert alternate.name_norm == "tunis"


async def test_the_geonames_name_is_folded_by_the_database_on_every_write(db_session):
    place = GeoName(geoname_id=1, name="Sidi Bou Saïd")
    db_session.add(place)
    await db_session.flush()
    await db_session.refresh(place)

    assert place.name_norm == "sidi bou said"

    place.name = "Hammam-Lif"
    await db_session.flush()
    await db_session.refresh(place)

    assert place.name_norm == "hammam lif"


async def test_the_migration_and_the_models_define_the_same_folding():
    spec = importlib.util.spec_from_file_location("add_search_columns", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    # The migration holds a frozen copy; while no later migration changes the
    # folding, the two must say the same.
    assert migration.NORMALIZE_NAME_SQL == NORMALIZE_NAME_SQL


async def test_a_pair_of_places_is_in_the_hierarchy_once(db_session):
    db_session.add_all([GeoName(geoname_id=1, name="Tunisia"), GeoName(geoname_id=2, name="Tunis")])
    db_session.add(GeoHierarchy(parent_id=1, child_id=2, hierarchy_type="ADM"))
    await db_session.flush()

    db_session.add(GeoHierarchy(parent_id=1, child_id=2))
    with pytest.raises(IntegrityError, match="uq_geonames_hierarchy_parent_child"):
        await db_session.flush()


async def explain(session, statement: str) -> str:
    # The tables here hold a handful of rows, where a sequential scan always
    # wins; this asks whether the index is usable at all for the query.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (await session.execute(text(f"EXPLAIN {statement}"))).scalars()
    return "\n".join(plan)


async def test_distance_queries_in_metres_can_use_the_geography_index(db_session):
    plan = await explain(
        db_session,
        "SELECT geoname_id FROM geodata.geonames "
        "WHERE ST_DWithin(location_geom::geography, "
        "ST_SetSRID(ST_MakePoint(10.18, 36.8), 4326)::geography, 25000)",
    )

    assert "ix_geonames_location_geog" in plan


async def test_places_are_found_by_the_start_of_their_folded_name_in_index_order(db_session):
    plan = await explain(
        db_session,
        "SELECT geoname_id FROM geodata.geonames "
        "WHERE name_norm ~>=~ 'san' AND name_norm ~<~ 'sao'",
    )

    assert "ix_geonames_name_norm_prefix" in plan


async def test_a_region_is_found_through_the_partial_index_on_adm1_rows(db_session):
    plan = await explain(
        db_session,
        "SELECT geoname_id FROM geodata.geonames "
        "WHERE country_code = 'TN' AND admin1_code = '23' AND feature_code = 'ADM1'",
    )

    assert "ix_geonames_adm1" in plan


async def test_folded_names_are_searched_by_trigram_and_by_prefix(db_session):
    fuzzy = await explain(
        db_session,
        "SELECT geoname_id FROM geodata.geonames_alternate_names WHERE name_norm % 'تونس'",
    )
    prefix = await explain(
        db_session,
        "SELECT geoname_id FROM geodata.geonames_alternate_names WHERE name_norm LIKE 'تو%'",
    )

    assert "ix_geonames_alternate_names_name_norm_trgm" in fuzzy
    assert "ix_geonames_alternate_names_name_norm_" in prefix
