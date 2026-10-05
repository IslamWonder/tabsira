"""Shared by the orphan tests: a small world with two places that have no region, and entries made straight in the database."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src import clock
from src.models import GeoName, MapEntry, MapEntryGeneralisation, MapEntryStatus
from src.models.atlas import LocationMeaning
from src.services import orphan_service
from src.storage.photos import build_photo_store
from tests import geo_dataset as world_data
from tests.geo_dataset import TUNIS_CITY

OLD = 60
BIGTOWN = 7000001
HAMLET = 7000002
HANDLE = "authorhandle"
WHOLE = {"west": -180, "south": -90, "east": 180, "north": 90}
NEAR_TUNIS = {"lat": 36.8, "lng": 10.18}


@pytest.fixture
async def world(db_session: AsyncSession, scripture: None) -> None:
    """The small world, and two Tunisian places with no region of their own to widen to."""
    await world_data.load_world(db_session)
    for geoname_id, name, lat, lng, population in (
        (BIGTOWN, "Bigtown", 35.0, 10.0, 50_000),
        (HAMLET, "Hamlet", 35.5, 9.5, 100),
    ):
        db_session.add(
            GeoName(
                **world_data.place(geoname_id, name, lat, lng, "P", "PPL", "TN", "99", population),
                location_geom=func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
            )
        )
    await db_session.flush()


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


async def fresh(db: AsyncSession, target: MapEntry | int) -> MapEntry:
    """
    The entry as the database holds it now, whichever session changed it.

    An integer is an id; an entry is found again by its insight, since widening gives an entry a
    new id.
    """
    condition = (
        MapEntry.id == target
        if isinstance(target, int)
        else (MapEntry.insight_id == target.insight_id)
        & (MapEntry.status != MapEntryStatus.WITHDRAWN)
    )
    found = await db.scalar(
        select(MapEntry).where(condition).execution_options(populate_existing=True)
    )
    assert found is not None
    return found


async def current_id(db: AsyncSession, insight_id: int) -> str:
    """The public id the insight's live entry has now, as a response gives it."""
    found = await db.scalar(
        select(MapEntry.id).where(
            MapEntry.insight_id == insight_id, MapEntry.status != MapEntryStatus.WITHDRAWN
        )
    )
    assert found is not None
    return str(found)


# (place, admin area, country code, country) as the atlas labels an entry placed there.
PLACE_LABELS: dict[int, tuple[str, str, str, str]] = {
    TUNIS_CITY: ("تونس", "ولاية تونس", "TN", "تونس"),
    world_data.MECCA_CITY: ("مكة المكرمة", "مكة المكرّمة", "SA", "السعودية"),
}


async def entry_row(
    db: AsyncSession,
    member: Any,
    *,
    place: int | None = TUNIS_CITY,
    lat: float = 36.8065,
    lng: float = 10.1815,
    status: MapEntryStatus = MapEntryStatus.PUBLISHED,
    age_days: int = OLD,
    **columns: Any,
) -> MapEntry:
    """A published entry straight in the database, last active `age_days` ago."""
    from tests.test_atlas import _insight

    moment = clock.utcnow() - timedelta(days=age_days)
    labels = PLACE_LABELS.get(
        place, (None, None, "TN" if place else None, "تونس" if place else None)
    )
    values: dict[str, Any] = {
        "user_id": member.user.id,
        "insight_id": await _insight(db, member),
        "public_lat": lat,
        "public_lng": lng,
        "public_geom": WKTElement(f"POINT({lng} {lat})", srid=4326),
        "cell_m": 1000,
        "location_meaning": LocationMeaning.CAPTURE_POINT,
        "place_geoname_id": place,
        "place_label": labels[0],
        "admin_label": labels[1],
        "country_iso2": labels[2],
        "country_label": labels[3],
        "status": status,
        "published_at": moment,
        "last_active_at": moment,
        **columns,
    }
    entry = MapEntry(**values)
    db.add(entry)
    await db.flush()
    return entry


async def run_job(
    factory: async_sessionmaker[AsyncSession], db: AsyncSession, make_settings, days: int = 30
) -> orphan_service.MarkReport:
    report = await orphan_service.mark_orphans(factory, days, build_photo_store(make_settings()))
    # The job ran in sessions of its own; the test's session must not answer from its memory.
    for held in [item for item in db.identity_map.values() if isinstance(item, MapEntry)]:
        db.expunge(held)
    return report


async def generalisations(db: AsyncSession, target: MapEntry | int) -> list[MapEntryGeneralisation]:
    entry_id = target if isinstance(target, int) else (await fresh(db, target)).id
    return list(
        await db.scalars(
            select(MapEntryGeneralisation)
            .where(MapEntryGeneralisation.entry_id == entry_id)
            .execution_options(populate_existing=True)
        )
    )
