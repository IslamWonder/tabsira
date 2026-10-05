"""
«كفالة بصيرة» (decision 60): an atlas entry nobody looks after turns orphaned, and its place widens.

A published entry with no sponsorship and no sign of life for `ORPHAN_AFTER_DAYS` is orphaned by
the daily job (`python -m src.cli.mark_orphans`). For each one, in one transaction, the public
place is widened to an area the entry cannot be told from its neighbours in, the earlier public
point, cell size and label are written to `map_entry_generalisations`, its photo copy goes, and
the entry is given a new public id (the old one encodes the millisecond it was placed, and
answers 410 from then on). Nothing here reads the private capture point.

The level is chosen from the area alone, never from how far its centre is from the earlier public
point: that distance would let the level betray where the hidden point was. From the coarsest of
the known areas down, the first whose cell is larger than the entry's own (a public figure) and
that is big enough to hide in:

1. the region (GeoNames ADM1) of the place the entry is labelled with, if it has at least
   `MIN_REGION_POPULATION` people;
2. the place itself when it is a city of at least `MIN_CITY_POPULATION` people;
3. the country, by its GeoNames centre;
4. a fixed grid cell, the first of `GRID_SIZES_M` that is at least `MIN_GRID_M` and twice the
   entry's own cell, taken as it falls: no distance test.

A centre that happens to be the earlier point is fine, since the cell, and so the doubt, grows.
Once an entry has a level it keeps it: a second marking (a sponsorship that ended and went quiet)
changes the state and nothing else, and `atlas_service.place` never narrows it.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from geoalchemy2.elements import WKTElement
from sqlalchemy import Select, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src import clock
from src.geo.privacy import MAX_CELL_METERS, METERS_PER_DEGREE, approximate
from src.models.atlas import (
    MapEntry,
    MapEntryGeneralisation,
    MapEntryRetiredId,
    MapEntrySponsorship,
    MapEntryStatus,
    WidenLevel,
)
from src.models.geonames import GeoCountryInfo, GeoName
from src.models.moderation import (
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    ModerationTarget,
)
from src.models.social import Report, ReportStatus, ReportTarget
from src.services import photo_service
from src.storage.photos import PhotoStore

REASON = "orphaned"
SUPERSEDED_REASON = "superseded_at_widening"
# A region of fewer people than this is no crowd to hide in (a governorate of a few thousand is a
# village's worth); a city needs fewer, since it is only one step up from the cell.
MIN_REGION_POPULATION = 100_000
MIN_CITY_POPULATION = 10_000
# The finest grid fallback; a coarser one is taken when the entry's own cell is already wide.
MIN_GRID_M = int(MAX_CELL_METERS)
# What `cell_m` says about a level: the rough size in metres of the area the point stands for.
LEVEL_CELL_M: dict[WidenLevel, int] = {
    WidenLevel.CITY: 20_000,
    WidenLevel.REGION: 100_000,
    WidenLevel.COUNTRY: 500_000,
}
# Grid fallbacks, finest first. The last one is taken when the entry's cell is wider than all.
GRID_SIZES_M = (int(MAX_CELL_METERS), 100_000, 200_000, 400_000, 800_000, 1_600_000)
_MIN_COSINE = 0.05
# An unpredictable order, from the operating system's generator.
_SHUFFLE = random.SystemRandom().shuffle


@dataclass(frozen=True)
class Widening:
    """The public side of an entry after its place is widened."""

    level: WidenLevel
    cell_m: int
    lat: float
    lng: float
    geoname_id: int | None
    place_label: str | None
    country_iso2: str | None
    country_label: str | None


class Marked(StrEnum):
    """What happened to one entry: left alone, orphaned as it was, or orphaned and widened."""

    SKIPPED = "skipped"
    ORPHANED = "orphaned"
    WIDENED = "widened"
    # Widened, but the store refused to delete the photo's public copy: counted as a failure.
    WIDENED_PHOTO_KEPT = "widened_photo_kept"


@dataclass
class MarkReport:
    """What one run did, in counts only: a report never names a place or an entry."""

    marked: int = 0
    widened: int = 0
    failed: int = 0


def _label(place: GeoName) -> str:
    return place.ar_name or place.name


def _wider(entry: MapEntry, cell_m: int) -> bool:
    """Whether a level's cell is larger than the entry's own; both are public figures."""
    return cell_m > entry.cell_m


async def _region_of(db: AsyncSession, place: GeoName) -> GeoName | None:
    """Return the first-level administrative area (ADM1) the place lies in, when GeoNames has it."""
    if place.country_code is None or place.admin1_code is None:
        return None
    return await db.scalar(
        select(GeoName)
        .where(
            GeoName.country_code == place.country_code,
            GeoName.admin1_code == place.admin1_code,
            GeoName.feature_code == "ADM1",
            GeoName.is_active.is_(True),
            GeoName.latitude.is_not(None),
            GeoName.longitude.is_not(None),
        )
        .order_by(GeoName.population.desc().nulls_last(), GeoName.geoname_id)
        .limit(1)
    )


async def _country_of(db: AsyncSession, iso2: str) -> GeoName | None:
    """Return the GeoNames record of a country, by its ISO code, when it has a centre."""
    info = await db.get(GeoCountryInfo, iso2)
    if info is None or info.geoname_id is None:
        return None
    return await db.scalar(
        select(GeoName).where(
            GeoName.geoname_id == info.geoname_id,
            GeoName.is_active.is_(True),
            GeoName.latitude.is_not(None),
            GeoName.longitude.is_not(None),
        )
    )


def _area(level: WidenLevel, area: GeoName, entry: MapEntry) -> Widening | None:
    """Widen to the centre of a GeoNames area; None when the area has no centre or is not wider."""
    if area.latitude is None or area.longitude is None:
        return None
    cell_m = LEVEL_CELL_M[level]
    if not _wider(entry, cell_m):
        return None
    return Widening(
        level,
        cell_m,
        area.latitude,
        area.longitude,
        area.geoname_id,
        _label(area),
        entry.country_iso2,
        entry.country_label,
    )


def _grid_centre(lat: float, lng: float, size_m: int) -> tuple[float, float]:
    """Return the centre of the grid cell of about `size_m` metres that holds the point."""
    if size_m <= MAX_CELL_METERS:
        centre = approximate(lat, lng, size_m)
        return centre.lat, centre.lng
    # Beyond the privacy grid's largest cell: rows of equal latitude, each cut into columns as
    # wide as the row is tall, which is plenty for an area that hides a place among its neighbours.
    step = size_m / METERS_PER_DEGREE
    row = math.floor((lat + 90) / step)
    centre_lat = min(90.0, max(-90.0, -90 + (row + 0.5) * step))
    wide = min(360.0, step / max(math.cos(math.radians(centre_lat)), _MIN_COSINE))
    column = math.floor((lng + 180) / wide)
    centre_lng = min(180.0, max(-180.0, -180 + (column + 0.5) * wide))
    return round(centre_lat, 6), round(centre_lng, 6)


def _grid(entry: MapEntry) -> Widening:
    """Widen to the first fixed grid size that is wide enough for this entry, whatever else is known."""
    lat = entry.public_lat if entry.public_lat is not None else 0.0
    lng = entry.public_lng if entry.public_lng is not None else 0.0
    wanted = max(MIN_GRID_M, 2 * entry.cell_m)
    size = next((size for size in GRID_SIZES_M if size >= wanted), GRID_SIZES_M[-1])
    return Widening(WidenLevel.GRID, size, *_grid_centre(lat, lng, size), None, None, None, None)


async def widening_of(db: AsyncSession, entry: MapEntry) -> Widening:
    """
    Choose how far to widen an entry's public place.

    Reads GeoNames and the entry's own public columns, never the capture point.
    """
    place = (
        await db.scalar(
            select(GeoName).where(
                GeoName.geoname_id == entry.place_geoname_id, GeoName.is_active.is_(True)
            )
        )
        if entry.place_geoname_id is not None
        else None
    )
    chosen: Widening | None = None
    if place is not None:
        region = await _region_of(db, place)
        if region is not None and (region.population or 0) >= MIN_REGION_POPULATION:
            chosen = _area(WidenLevel.REGION, region, entry)
        if chosen is None and (place.population or 0) >= MIN_CITY_POPULATION:
            chosen = _area(WidenLevel.CITY, place, entry)
    if chosen is None and entry.country_iso2:
        country = await _country_of(db, entry.country_iso2)
        chosen = None if country is None else _area(WidenLevel.COUNTRY, country, entry)
    return chosen if chosen is not None else _grid(entry)


def _apply(entry: MapEntry, widening: Widening) -> None:
    """Replace the public side of the entry with the widened one."""
    entry.public_lat = round(widening.lat, 6)
    entry.public_lng = round(widening.lng, 6)
    entry.public_geom = WKTElement(f"POINT({entry.public_lng} {entry.public_lat})", srid=4326)
    entry.cell_m = widening.cell_m
    entry.place_geoname_id = widening.geoname_id
    entry.place_label = widening.place_label
    entry.admin_label = None
    entry.country_iso2 = widening.country_iso2
    entry.country_label = widening.country_label
    entry.widened_level = widening.level


async def _reissue_id(db: AsyncSession, entry: MapEntry) -> None:
    """
    Give the entry a new public id and retire the old one.

    A public id is the millisecond it was made, so the old one would still say when the entry was
    placed. The rows that name the entry follow the change (`ON UPDATE CASCADE`). Reports are
    different: one that followed would let a reporter's answer link the old id to the new, so the
    open reports of the old address are closed as superseded and stay with it, and a report of the
    new address is a fresh one. One row of the moderation log, under the old id, says so; the new
    id is written nowhere beside the entry. The old address answers 410 from now on. The caller's
    copy of the entry is stale afterwards.
    """
    old_id = entry.id
    new_id = (await db.execute(text("SELECT app.timestamp_id('map_entries'::text)"))).scalar_one()
    db.add(MapEntryRetiredId(id=old_id))
    db.add(
        ModerationAction(
            target_type=ModerationTarget.MAP_ENTRY,
            target_id=old_id,
            action=ModerationActionKind.SUPERSEDED,
            source=ModerationSource.JOB,
            reason=SUPERSEDED_REASON,
        )
    )
    await db.flush()
    await db.execute(
        update(MapEntry)
        .where(MapEntry.id == old_id)
        .values(id=new_id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        update(Report)
        .where(
            Report.target_type == ReportTarget.MAP_ENTRY,
            Report.target_id == old_id,
            Report.status == ReportStatus.OPEN,
        )
        .values(status=ReportStatus.DISMISSED, handled_at=clock.utcnow())
        .execution_options(synchronize_session=False)
    )
    db.expunge(entry)


def due(cutoff: datetime) -> Select[int]:
    """Select the ids of published entries nobody sponsors that have gone quiet since `cutoff`."""
    sponsored = (
        select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id == MapEntry.id).exists()
    )
    return select(MapEntry.id).where(
        MapEntry.status == MapEntryStatus.PUBLISHED, MapEntry.last_active_at < cutoff, ~sponsored
    )


async def mark_one(db: AsyncSession, entry_id: int, cutoff: datetime, store: PhotoStore) -> Marked:
    """
    Orphan one entry in the caller's transaction, and say what was done.

    The row is locked and read again: the author may have placed it again, or someone may have
    started to look after it, since the batch was selected. Then nothing is changed and nothing is
    recorded. An entry that already has a level keeps it, and its id.
    """
    entry = await db.scalar(
        select(MapEntry).where(MapEntry.id == entry_id).with_for_update(skip_locked=True)
    )
    if entry is None or entry.status is not MapEntryStatus.PUBLISHED:
        return Marked.SKIPPED
    if entry.last_active_at >= cutoff:
        return Marked.SKIPPED
    if await db.scalar(
        select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id == entry.id)
    ):
        return Marked.SKIPPED
    entry.status = MapEntryStatus.ORPHANED
    entry.status_reason = None
    if entry.widened_level is not None:
        await db.flush()
        return Marked.ORPHANED
    widening = await widening_of(db, entry)
    db.add(
        MapEntryGeneralisation(
            entry_id=entry.id,
            previous_cell_m=entry.cell_m,
            previous_public_lat=entry.public_lat,
            previous_public_lng=entry.public_lng,
            previous_place_label=entry.place_label,
            new_level=widening.level,
            new_label=widening.place_label,
            reason=REASON,
        )
    )
    shown_photo = entry.with_photo
    insight_id = entry.insight_id
    _apply(entry, widening)
    # A photo could say where the place is: it is not shown again, whoever looks after the entry.
    entry.with_photo = False
    await db.flush()
    await _reissue_id(db, entry)
    if shown_photo and not await photo_service.sync_public_copy(db, store, insight_id, retry=False):
        return Marked.WIDENED_PHOTO_KEPT
    return Marked.WIDENED


def cutoff_for(days: int) -> datetime:
    """
    Return the moment before which an entry's last sign of life makes it quiet.

    The start of a UTC day, not "now minus the days": a widened entry gets a new public id when
    the job reaches it, and an id made at a time that moves with the clock of the run would tell
    how long the entry had been quiet.
    """
    today = clock.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=days)


async def mark_orphans(
    factory: async_sessionmaker[AsyncSession],
    days: int,
    store: PhotoStore,
    shuffle: Callable[[list[int]], None] = _SHUFFLE,
) -> MarkReport:
    """
    Orphan every entry that went quiet, one transaction for each.

    The entries are taken in random order: the new public ids are made one after the other, and
    in the order of the old ones they would keep the order in which the entries were placed. An
    entry that fails is counted and left for the next run; it never stops the others.
    """
    report = MarkReport()
    cutoff = cutoff_for(days)
    async with factory() as db:
        ids = list(await db.scalars(due(cutoff)))
    shuffle(ids)
    for entry_id in ids:
        try:
            async with factory() as db, db.begin():
                marked = await mark_one(db, entry_id, cutoff, store)
        except Exception:  # one entry's failure must not stop the rest
            report.failed += 1
            continue
        report.marked += marked is not Marked.SKIPPED
        report.widened += marked in {Marked.WIDENED, Marked.WIDENED_PHOTO_KEPT}
        report.failed += marked is Marked.WIDENED_PHOTO_KEPT
    return report
