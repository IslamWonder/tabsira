"""
Placing an insight on the atlas, publishing it, withdrawing it, and reading what is public.

The private and the public location never meet in a public answer. An owner gives the exact
point; the server rounds it to the centre of a grid cell (`src/geo/privacy.py`, the size from
`GEO_APPROX_CELL_METERS`) and labels it with the nearest populated place, found from the
public point, never from the private one. Public queries read `map_entries` alone and filter
on the public point; `map_capture_points` is read by the owner's routes and the export only.

An entry is made from one of the owner's own insights that came out of the real pipeline
(the social network applies the same rule, `insight_table_source.PUBLISHABLE_ENGINE`). Only
an account with a public identity publishes, since the atlas names the author as the posts do.

An orphaned entry (decision 60) is read through the same functions: its place was widened by
`orphan_service`, it carries no author, and `place` keeps the widened place whatever the author
does afterwards. Only the sponsor, when there is one, is named beside it.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from geoalchemy2 import Geography
from geoalchemy2.elements import WKTElement
from sqlalchemy import Float, Integer, Select, cast, delete, exists, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from src import clock
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.geo.privacy import METERS_PER_DEGREE, approximate, cell_polygon
from src.messages import messages_for
from src.models.atlas import (
    LocationMeaning,
    MapCapturePoint,
    MapEntry,
    MapEntryGeneralisation,
    MapEntryRetiredId,
    MapEntrySponsorship,
    MapEntryStatus,
    WidenLevel,
)
from src.models.geonames import GeoName
from src.models.scan import Insight, Scan
from src.models.social import (
    CommentStatus,
    InsightPublication,
    Post,
    PostStatus,
    PostVisibility,
)
from src.models.user import User
from src.schemas.atlas import (
    AtlasClusterCollection,
    AtlasClusterFeature,
    AtlasClusterProperties,
    AtlasEntriesPage,
    AtlasEntryFeature,
    AtlasEntryOut,
    AtlasEntryProperties,
    AtlasFeature,
    AtlasFeatureProperties,
    AtlasOrphansOut,
    AtlasPlaceOut,
    CapturePointIn,
    CapturePointOut,
    GeoJsonPolygon,
    MapEntryOwnerOut,
    PlaceRef,
    PublicLocationOut,
    PublicLocationPreview,
    WidenedOut,
)
from src.schemas.geo import GeoJsonPoint
from src.schemas.social import MemberOut
from src.services import cursor as cursors
from src.services import geo_service, photo_service, public_identity, publication_service
from src.services.block_service import blocked_with
from src.services.evidence_view import load_evidence
from src.services.insight_table_source import explanation_excerpt, snapshot_of
from src.services.insight_view import visible_parts, visible_step
from src.services.post_view import outcome_message
from src.storage.photos import PhotoStore

# Entries returned for one map window at most; the client asks again for a smaller window.
WINDOW_DEFAULT = 300
WINDOW_MAX = 1000
# Groups: a grid cell is about this many CSS pixels wide on screen, whatever the zoom.
CLUSTER_CELL_PX = 60
# From this zoom on nothing is grouped: every visible entry is its own point.
CLUSTER_OFF_ZOOM = 16
# Features in one cluster answer at most; `truncated` says there were more.
CLUSTER_FEATURES_MAX = 500
_MERCATOR_TILE_PX = 256
_MERCATOR_HALF_M = 20_037_508.342789244
# Web Mercator stops here; a point nearer the pole is placed in the last row of cells.
_MERCATOR_MAX_LAT = 85.0511287798
# A cursor holds a distance, not a time; `at` is a fixed one so that the shared cursor fits.
_DISTANCE_CURSOR_AT = datetime(1970, 1, 1, tzinfo=UTC)
# The cluster and page queries scan a window: one that runs longer than this is cut, not queued.
QUERY_TIMEOUT_MS = 3_000
_QUERY_CANCELED = "57014"
PLACE_PAGE_DEFAULT = 20
PLACE_PAGE_MAX = 50
ORPHAN_RADIUS_DEFAULT_M = 150_000
# A widened place is tens of kilometres wide at least: a smaller radius would find nothing.
ORPHAN_RADIUS_MIN_M = 10_000
ORPHAN_RADIUS_MAX_M = 500_000
# The position a viewer sends is snapped to this grid (about 0.05 degrees, like the camera's window)
# before it is used, so that the queries never hold the point itself.
ORPHAN_QUERY_CELL_M = 5_550
# Never nearer than this to the pole or the antimeridian when a box is used to prefilter.
_MIN_COSINE = 0.05


@dataclass(frozen=True)
class Window:
    """A map window in degrees; `west > east` means it crosses the antimeridian."""

    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class Filters:
    since: date | None = None
    country: str | None = None
    concept: str | None = None


def not_found() -> AppError:
    return AppError(ErrorCode.NOT_FOUND, "No such map entry.", status_code=404)


def gone() -> AppError:
    return AppError(ErrorCode.GONE, "This map entry was withdrawn.", status_code=410)


def _wrong_state(message: str) -> AppError:
    return AppError(ErrorCode.CONFLICT, message, status_code=409)


def precision_label(cell_m: int, level: WidenLevel | None = None) -> str:
    """Say how precise a public place is: a size for a cell, a level for a widened place."""
    if level is not None:
        return messages_for().atlas_levels[level.value]
    return messages_for().atlas_precision.format(metres=cell_m)


def meaning_label(meaning: LocationMeaning) -> str:
    return messages_for().atlas_meanings[meaning.value]


def _point(lat: float, lng: float) -> GeoJsonPoint:
    return GeoJsonPoint(coordinates=[lng, lat])


def place_of(entry: MapEntry) -> PlaceRef | None:
    if entry.place_geoname_id is None or entry.place_label is None:
        return None
    return PlaceRef(
        geoname_id=entry.place_geoname_id,
        label=entry.place_label,
        admin_label=entry.admin_label,
        country_iso2=entry.country_iso2,
        country_label=entry.country_label,
    )


def public_location(entry: MapEntry) -> PublicLocationOut | None:
    if entry.public_lat is None or entry.public_lng is None:
        return None
    return PublicLocationOut(
        point=_point(entry.public_lat, entry.public_lng),
        cell_m=entry.cell_m,
        precision_label=precision_label(entry.cell_m, entry.widened_level),
        meaning=entry.location_meaning,
        meaning_label=meaning_label(entry.location_meaning),
        widened_level=entry.widened_level,
    )


def _author(user: User) -> MemberOut:
    return MemberOut(handle=user.handle or "", public_name=public_identity.shown_name(user))


def _shown_author(entry: MapEntry, user: User) -> MemberOut | None:
    """Name the author unless the place was widened: an orphaned entry is anonymous for good."""
    return None if entry.widened_level is not None else _author(user)


@dataclass(frozen=True)
class Sponsor:
    """Who looks after an entry, and the words they published under it (never a held one)."""

    member: MemberOut
    # The sponsorship's public id, and the words once published: a report names them by it.
    sponsorship_id: int
    reflection: str | None


async def sponsors_of(
    db: AsyncSession, entry_ids: list[int], viewer: User | None
) -> dict[int, Sponsor]:
    """
    Return the open sponsor of each of the entries, by entry id.

    The sponsor chose to sponsor in public, so the handle is shown; one a block stands between
    and the viewer is left out, as everywhere, and so is one whose account is closed. The
    reflection is the sponsor's only once the guard or a moderator published it.
    """
    if not entry_ids:
        return {}
    statement = (
        select(MapEntrySponsorship, User)
        .join(User, User.id == MapEntrySponsorship.user_id)
        .where(
            MapEntrySponsorship.entry_id.in_(entry_ids),
            *_visible_author(),
        )
    )
    if viewer is not None:
        statement = statement.where(User.id.not_in(blocked_with(viewer.id)))
    return {
        sponsorship.entry_id: Sponsor(
            member=_author(sponsor),
            sponsorship_id=sponsorship.id,
            reflection=(
                sponsorship.reflection
                if sponsorship.reflection_status is CommentStatus.PUBLISHED
                else None
            ),
        )
        for sponsorship, sponsor in (await db.execute(statement))
    }


async def _sponsors(
    db: AsyncSession, entry_ids: list[int], viewer: User | None, sponsoring: bool
) -> dict[int, Sponsor]:
    """Return the sponsors, or none while sponsoring is switched off: the atlas then knows none."""
    return await sponsors_of(db, entry_ids, viewer) if sponsoring else {}


# ─── The owner's side ───


async def _own_insight(db: AsyncSession, user: User, insight_id: int) -> Insight:
    """Return the caller's insight, or the 404 of one that does not exist."""
    insight = await db.scalar(
        select(Insight).where(Insight.id == insight_id, Insight.user_id == user.id)
    )
    if insight is None:
        raise AppError(ErrorCode.NOT_FOUND, "No such insight.", status_code=404)
    return insight


async def _check_publishable(db: AsyncSession, insight: Insight) -> None:
    """
    Apply the posts' rule here too: not under 13, verified, texts clean, evidence eligible.

    An account that declared itself under 13 places no location at all (extension §10, v2 §5):
    `publication_service` refuses it with `UNDER_13_CANNOT_PUBLISH`, a declared fact, never
    an inference.
    """
    scan = await db.get(Scan, insight.scan_id) if insight.scan_id is not None else None
    await publication_service.check_publishable(db, snapshot_of(insight, scan))


def _live(insight_id: int) -> ColumnElement[bool]:
    """Select the one entry of an insight that is not a withdrawn tombstone."""
    return (MapEntry.insight_id == insight_id) & (MapEntry.status != MapEntryStatus.WITHDRAWN)


async def _own_entry(db: AsyncSession, user: User, insight_id: int) -> tuple[MapEntry, Insight]:
    insight = await _own_insight(db, user, insight_id)
    entry = await db.scalar(select(MapEntry).where(_live(insight.id)))
    if entry is None:
        raise not_found()
    return entry, insight


async def _label(db: AsyncSession, lat: float, lng: float) -> dict[str, object]:
    """Return the nearest populated place of the *public* point: the label hides what the cell hides."""
    found = await geo_service.nearest_place(db, lat, lng)
    if found.place is None:
        return {
            "place_geoname_id": None,
            "place_label": None,
            "admin_label": None,
            "country_iso2": None,
            "country_label": None,
        }
    return {
        "place_geoname_id": found.place.geoname_id,
        "place_label": found.place.label,
        "admin_label": found.admin_area.label if found.admin_area else None,
        "country_iso2": found.country.iso2 if found.country else None,
        "country_label": found.country.label if found.country else None,
    }


async def place(
    db: AsyncSession,
    settings: Settings,
    user: User,
    insight_id: int,
    body: CapturePointIn,
    *,
    photos: PhotoStore | None = None,
) -> MapEntryOwnerOut:
    """
    Keep the owner's exact point privately and compute what the map will show.

    The entry is a draft until the owner publishes it; placing a published entry again
    makes it a draft again, since what is shown changed. The cell size is the setting's at
    the time of placing, kept with the entry. With `photos`, a public copy that only the
    entry showed is deleted with the draft, whatever the new choice of photo.

    An entry whose place was widened (decision 60) is never narrowed: the owner's new point
    replaces the private one, and the public point, the cell and the labels stay as widened. The
    photo is not shown either, since it could say where the place is. An entry a member
    sponsors cannot be placed again while the sponsorship stands: 409.
    """
    insight = await _own_insight(db, user, insight_id)
    await _check_publishable(db, insight)
    cell_m = int(settings.geo_approx_cell_meters)
    centre = approximate(body.latitude, body.longitude, cell_m)
    labels = await _label(db, centre.lat, centre.lng)
    # Locked and read fresh: the daily job widening it, or a member sponsoring it, must be seen
    # below, not guessed from an earlier read.
    entry = await db.scalar(
        select(MapEntry)
        .where(_live(insight.id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    decided = {MapEntryStatus.PENDING_REVIEW, MapEntryStatus.REMOVED}
    if entry is not None and entry.status in decided:
        message = "A moderator's decision stands on this entry; it cannot be placed again."
        raise _wrong_state(message)
    if entry is not None and await is_sponsored(db, entry.id):
        message = "A member sponsors this entry; it cannot be placed again while they do."
        raise _wrong_state(message)
    if entry is None:
        # A withdrawn tombstone may stand beside it: the new entry takes a new address.
        entry = MapEntry(user_id=user.id, insight_id=insight.id, cell_m=cell_m)
        db.add(entry)
    widened = entry.widened_level is not None
    if not widened:
        entry.public_lat = centre.lat
        entry.public_lng = centre.lng
        entry.public_geom = WKTElement(f"POINT({centre.lng} {centre.lat})", srid=4326)
        entry.cell_m = cell_m
        for column, value in labels.items():
            setattr(entry, column, value)
    entry.location_meaning = body.meaning
    entry.with_photo = body.photo and not widened
    entry.last_active_at = clock.utcnow()
    entry.status = MapEntryStatus.DRAFT
    entry.status_reason = None
    # `published_at` is kept: it records that the address was once public, so that a later
    # withdrawal leaves the tombstone (410) a once-shared address needs; publishing sets it anew.
    entry.withdrawn_at = None
    await db.flush()
    point = await db.get(MapCapturePoint, entry.id)
    if point is None:
        point = MapCapturePoint(entry_id=entry.id)
        db.add(point)
    point.latitude = body.latitude
    point.longitude = body.longitude
    point.accuracy_m = body.accuracy_m
    point.source = body.source
    point.captured_at = body.captured_at
    point.measured_at = body.measured_at
    point.confirmed_at = clock.utcnow()
    await db.flush()
    if photos is not None:
        await photo_service.sync_public_copy(db, photos, insight.id)
    return owner_view(entry, insight, point)


async def is_sponsored(db: AsyncSession, entry_id: int) -> bool:
    return bool(
        await db.scalar(
            select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id == entry_id)
        )
    )


async def widenings_of(db: AsyncSession, entry_ids: list[int]) -> dict[int, MapEntryGeneralisation]:
    """Return the latest widening record of each entry that has one; for its owner's view only."""
    rows = await db.scalars(
        select(MapEntryGeneralisation)
        .where(MapEntryGeneralisation.entry_id.in_(entry_ids))
        .order_by(MapEntryGeneralisation.id)
    )
    return {record.entry_id: record for record in rows}


def owner_view(
    entry: MapEntry,
    insight: Insight,
    point: MapCapturePoint | None,
    sponsor: Sponsor | None = None,
    widening: MapEntryGeneralisation | None = None,
) -> MapEntryOwnerOut:
    public = public_location(entry)
    preview = None
    if public is not None and point is not None:
        # A widened place has no cell: the private point's cell would say where it lies.
        polygon = (
            None
            if entry.widened_level is not None
            else cell_polygon(point.latitude, point.longitude, entry.cell_m)
        )
        preview = PublicLocationPreview(
            **public.model_dump(),
            cell=None if polygon is None else GeoJsonPolygon(coordinates=polygon["coordinates"]),
        )
    return MapEntryOwnerOut(
        id=entry.id,
        insight_id=entry.insight_id,
        title=insight.title,
        status=entry.status,
        status_message=outcome_message(entry.status.value, entry.status_reason),
        capture=(
            None
            if point is None
            else CapturePointOut(
                latitude=point.latitude,
                longitude=point.longitude,
                accuracy_m=point.accuracy_m,
                source=point.source,
                captured_at=point.captured_at,
                measured_at=point.measured_at,
                confirmed_at=point.confirmed_at,
            )
        ),
        public=preview,
        place=place_of(entry),
        photo=entry.with_photo,
        sponsor=None if sponsor is None else sponsor.member,
        widened=(
            None
            if widening is None
            else WidenedOut(
                level=widening.new_level, label=widening.new_label, at=widening.created_at
            )
        ),
        published_at=entry.published_at,
        withdrawn_at=entry.withdrawn_at,
        created_at=entry.created_at,
    )


async def mine(db: AsyncSession, user: User, insight_id: int) -> MapEntryOwnerOut:
    entry, insight = await _own_entry(db, user, insight_id)
    sponsor = (await sponsors_of(db, [entry.id], user)).get(entry.id)
    widening = (await widenings_of(db, [entry.id])).get(entry.id)
    return owner_view(entry, insight, await db.get(MapCapturePoint, entry.id), sponsor, widening)


async def list_mine(db: AsyncSession, user: User) -> list[MapEntryOwnerOut]:
    rows = await db.execute(
        select(MapEntry, Insight, MapCapturePoint)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .outerjoin(MapCapturePoint, MapCapturePoint.entry_id == MapEntry.id)
        .where(MapEntry.user_id == user.id)
        .order_by(MapEntry.created_at.desc(), MapEntry.id.desc())
    )
    found = rows.all()
    ids = [entry.id for entry, _, _ in found]
    sponsors = await sponsors_of(db, ids, user)
    widenings = await widenings_of(db, ids)
    return [
        owner_view(entry, insight, point, sponsors.get(entry.id), widenings.get(entry.id))
        for entry, insight, point in found
    ]


async def publish(
    db: AsyncSession, user: User, insight_id: int, *, photos: PhotoStore
) -> MapEntryOwnerOut:
    """
    Show the entry on the atlas; a draft with a point only.

    When the owner chose to show the photo, its public copy is made now under the photo rules
    checked again (`photo_service`); the public map says nothing of it yet.
    """
    entry, insight = await _own_entry(db, user, insight_id)
    if entry.status is not MapEntryStatus.DRAFT or entry.public_lat is None:
        message = "Only a placed draft can be published."
        raise _wrong_state(message)
    # Checked again: a ruling may have changed since the entry was placed.
    await _check_publishable(db, insight)
    entry.status = MapEntryStatus.PUBLISHED
    entry.published_at = clock.utcnow()
    entry.last_active_at = entry.published_at
    await db.flush()
    if entry.with_photo:
        await photo_service.sync_public_copy(db, photos, insight.id)
    return owner_view(entry, insight, await db.get(MapCapturePoint, entry.id))


async def withdraw(db: AsyncSession, user: User, insight_id: int, *, photos: PhotoStore) -> None:
    """
    Take the entry off the atlas and forget the exact point.

    The public point is cleared too: nothing of the location survives but the tombstone that
    makes the entry's address answer 410. The public copy of the photo goes unless a live post
    still shows it.
    """
    insight = await _own_insight(db, user, insight_id)
    entry = await db.scalar(select(MapEntry).where(_live(insight.id)))
    if entry is None:
        # Nothing live: withdrawn already, or never placed. The same answer either way.
        return
    point = await db.get(MapCapturePoint, entry.id)
    if point is not None:
        await db.delete(point)
    if entry.published_at is None:
        # Never public (re-placing keeps the time): no address to keep, so no tombstone that
        # would say it existed.
        await db.delete(entry)
        await db.flush()
        return
    # The sponsor's words go with the entry, and so does the earlier cell: neither outlives it.
    await drop_sponsorships(db, entry.id)
    await db.execute(
        delete(MapEntryGeneralisation).where(MapEntryGeneralisation.entry_id == entry.id)
    )
    _clear_public_side(entry)
    await db.flush()
    if entry.with_photo:
        await photo_service.sync_public_copy(db, photos, insight.id)


async def drop_sponsorships(db: AsyncSession, entry_id: int) -> None:
    """Delete the entry's sponsorship, the sponsor's reflection with it: the words were for the entry."""
    await db.execute(delete(MapEntrySponsorship).where(MapEntrySponsorship.entry_id == entry_id))


def _clear_public_side(entry: MapEntry) -> None:
    """Leave the withdrawn tombstone: no point, no label, no place."""
    entry.status = MapEntryStatus.WITHDRAWN
    entry.status_reason = None
    entry.withdrawn_at = clock.utcnow()
    entry.public_lat = None
    entry.public_lng = None
    entry.public_geom = None
    for column in (
        "place_geoname_id",
        "place_label",
        "admin_label",
        "country_iso2",
        "country_label",
    ):
        setattr(entry, column, None)


# ─── The public side ───


def _visible_author() -> list[ColumnElement[bool]]:
    return [User.is_active.is_(True), User.deleted_at.is_(None), User.handle.isnot(None)]


def _envelopes(window: Window) -> ColumnElement[bool]:
    """Return the window as PostGIS envelopes; one that crosses the antimeridian is two."""
    south, north = min(window.south, window.north), max(window.south, window.north)
    if window.west <= window.east:
        return func.ST_Intersects(
            MapEntry.public_geom,
            func.ST_MakeEnvelope(window.west, south, window.east, north, 4326),
        )
    return or_(
        func.ST_Intersects(
            MapEntry.public_geom, func.ST_MakeEnvelope(window.west, south, 180, north, 4326)
        ),
        func.ST_Intersects(
            MapEntry.public_geom, func.ST_MakeEnvelope(-180, south, window.east, north, 4326)
        ),
    )


def _published_on(entry: MapEntry) -> date:
    """Return the day an entry was published, in UTC: a day, never an hour, so no trail is drawn."""
    moment = entry.published_at if entry.published_at is not None else entry.created_at
    return moment.astimezone(UTC).date()


def _published_day() -> ColumnElement[datetime]:
    """
    Return the day of publication in UTC, as `published_on` shows it.

    The public lists are ordered by it, then by id, so that a cursor carries the day and the id
    alone and never the hour.
    """
    return func.date_trunc("day", MapEntry.published_at, "UTC")


def _day_start(entry: MapEntry) -> datetime:
    return datetime.combine(_published_on(entry), time.min, tzinfo=UTC)


def _feature(
    entry: MapEntry,
    insight: Insight,
    author: User,
    sponsor: Sponsor | None = None,
    *,
    sponsoring: bool = True,
) -> AtlasFeature:
    # A published entry always has its point (a database constraint); the checks keep mypy honest.
    lat = entry.public_lat if entry.public_lat is not None else 0.0
    lng = entry.public_lng if entry.public_lng is not None else 0.0
    return AtlasFeature(
        id=entry.id,
        geometry=_point(lat, lng),
        properties=AtlasFeatureProperties(
            id=entry.id,
            title=insight.title,
            glimpse=insight.glimpse,
            author=_shown_author(entry, author),
            place=place_of(entry),
            cell_m=entry.cell_m,
            precision_label=precision_label(entry.cell_m, entry.widened_level),
            published_on=_published_on(entry),
            orphaned=sponsoring and entry.status is MapEntryStatus.ORPHANED,
            widened_level=entry.widened_level,
            sponsor=None if sponsor is None else sponsor.member,
        ),
    )


def _not_hidden_by_a_block(viewer: User) -> ColumnElement[bool]:
    """
    Match the entries a block does not hide from `viewer`.

    A block between the viewer and an entry's author hides it, except once its place was widened:
    the author is anonymous then, and a block that hid the entry would tell the blocker, by
    its absence, who wrote it. A block against the sponsor hides the entry, since the sponsor is
    named beside it.
    """
    blocked = blocked_with(viewer.id)
    by_author = MapEntry.widened_level.is_(None) & User.id.in_(blocked)
    by_sponsor = exists().where(
        MapEntrySponsorship.entry_id == MapEntry.id, MapEntrySponsorship.user_id.in_(blocked)
    )
    return ~(by_author | by_sponsor)


def _visible(
    statement: Select[Any], filters: Filters, viewer: User | None, *, sponsoring: bool
) -> Select[Any]:
    """
    Keep what this viewer may see on the map: the one rule every public read applies.

    The statement joins `Insight` and `User` to the entry. With sponsoring switched off an
    orphaned entry is served as the plain, anonymous, widened entry it is, so that it does not
    vanish; with it on, orphans are asked for by name.
    """
    shown = (
        [MapEntryStatus.PUBLISHED]
        if sponsoring
        else [MapEntryStatus.PUBLISHED, MapEntryStatus.ORPHANED]
    )
    statement = statement.where(MapEntry.status.in_(shown), *_visible_author())
    if viewer is not None:
        statement = statement.where(_not_hidden_by_a_block(viewer))
    if filters.since is not None:
        statement = statement.where(
            MapEntry.published_at >= datetime.combine(filters.since, time.min, tzinfo=UTC)
        )
    if filters.country is not None:
        statement = statement.where(MapEntry.country_iso2 == filters.country.upper())
    if filters.concept is not None:
        statement = statement.where(Insight.entity_ids.contains([filters.concept]))
    return statement


def _joined(*columns: Any) -> Select[Any]:
    return (
        select(*columns)
        .select_from(MapEntry)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .join(User, User.id == MapEntry.user_id)
    )


def _published_rows(filters: Filters, viewer: User | None, *, sponsoring: bool = True):  # type: ignore[no-untyped-def]
    statement = _visible(_joined(MapEntry, Insight, User), filters, viewer, sponsoring=sponsoring)
    return statement.order_by(_published_day().desc(), MapEntry.id.desc())


async def features_in(
    db: AsyncSession,
    window: Window,
    filters: Filters,
    limit: int,
    viewer: User | None = None,
    *,
    sponsoring: bool = True,
) -> tuple[list[AtlasFeature], bool]:
    """Return the published entries inside the window, newest first, and whether more were left out."""
    rows = (
        await db.execute(
            _published_rows(filters, viewer, sponsoring=sponsoring)
            .where(_envelopes(window))
            .limit(limit + 1)
        )
    ).all()
    sponsors = await _sponsors(db, [entry.id for entry, _, _ in rows[:limit]], viewer, sponsoring)
    features = [
        _feature(entry, insight, author, sponsors.get(entry.id), sponsoring=sponsoring)
        for entry, insight, author in rows[:limit]
    ]
    return features, len(rows) > limit


def _cell_index(merc_axis, across: int, cell_m: float):  # type: ignore[no-untyped-def]
    """Return the column or row of a Mercator coordinate in a grid of `across` cells."""
    index = func.floor((merc_axis + _MERCATOR_HALF_M) / cell_m)
    return cast(func.least(index, across - 1), Integer)


def _grid(zoom: int) -> tuple[int, float]:
    """
    Return how many cells span the world at a zoom, and the cell's side in metres.

    A cell is about `CLUSTER_CELL_PX` screen pixels: 60 x 156543.03392 / 2^zoom metres in Web
    Mercator. The count is rounded to a whole number so that no cell straddles the antimeridian,
    where a mean of longitudes would land on the wrong side of the world.
    """
    across = max(1, round(_MERCATOR_TILE_PX * 2**zoom / CLUSTER_CELL_PX))
    return across, 2 * _MERCATOR_HALF_M / across


def _as_entry_feature(feature: AtlasFeature) -> AtlasEntryFeature:
    return AtlasEntryFeature(
        id=feature.id,
        geometry=feature.geometry,
        properties=AtlasEntryProperties(**feature.properties.model_dump()),
    )


async def _entries_by_id(
    db: AsyncSession,
    entry_ids: list[int],
    filters: Filters,
    viewer: User | None,
    sponsoring: bool,
) -> dict[int, AtlasEntryFeature]:
    """Return the visible entries among `entry_ids` as map features, with their sponsors."""
    if not entry_ids:
        return {}
    rows = (
        await db.execute(
            _published_rows(filters, viewer, sponsoring=sponsoring).where(
                MapEntry.id.in_(entry_ids)
            )
        )
    ).all()
    sponsors = await _sponsors(db, [entry.id for entry, _, _ in rows], viewer, sponsoring)
    return {
        entry.id: _as_entry_feature(
            _feature(entry, insight, author, sponsors.get(entry.id), sponsoring=sponsoring)
        )
        for entry, insight, author in rows
    }


async def _clusters(
    db: AsyncSession,
    window: Window,
    filters: Filters,
    zoom: int,
    viewer: User | None = None,
    *,
    sponsoring: bool = True,
) -> AtlasClusterCollection:
    """
    Return the visible entries of a window grouped by grid cell, and the lone ones as entries.

    Only public points are read: a group sits at the mean of its members' public points, so no
    exact point can be found from it, and its properties hold a count and a box, never an id,
    an author or a time. The same rules as `features_in` decide what is counted, blocks included.
    From `CLUSTER_OFF_ZOOM` on every entry is returned as itself.
    """
    if zoom >= CLUSTER_OFF_ZOOM:
        entries, more = await features_in(
            db, window, filters, CLUSTER_FEATURES_MAX, viewer, sponsoring=sponsoring
        )
        return AtlasClusterCollection(
            features=[_as_entry_feature(feature) for feature in entries], truncated=more
        )
    across, cell_m = _grid(zoom)
    lat = func.greatest(func.least(MapEntry.public_lat, _MERCATOR_MAX_LAT), -_MERCATOR_MAX_LAT)
    merc = func.ST_Transform(
        func.ST_SetSRID(func.ST_MakePoint(MapEntry.public_lng, lat), 4326), 3857
    )
    column = _cell_index(func.ST_X(merc), across, cell_m).label("cell_x")
    row = _cell_index(func.ST_Y(merc), across, cell_m).label("cell_y")
    members = func.count().label("members")
    statement = (
        _visible(
            _joined(
                column,
                row,
                members,
                func.avg(MapEntry.public_lng).label("mean_lng"),
                func.avg(MapEntry.public_lat).label("mean_lat"),
                func.min(MapEntry.public_lng).label("west"),
                func.min(MapEntry.public_lat).label("south"),
                func.max(MapEntry.public_lng).label("east"),
                func.max(MapEntry.public_lat).label("north"),
                # Only read for a cell of one entry, to fetch it; never put in a group.
                func.min(MapEntry.id).label("only_id"),
            ),
            filters,
            viewer,
            sponsoring=sponsoring,
        )
        .where(_envelopes(window))
        .group_by(column, row)
        .order_by(members.desc(), column, row)
        .limit(CLUSTER_FEATURES_MAX + 1)
    )
    found = (await db.execute(statement)).all()
    truncated = len(found) > CLUSTER_FEATURES_MAX
    cells = found[:CLUSTER_FEATURES_MAX]
    singles = await _entries_by_id(
        db, [cell.only_id for cell in cells if cell.members == 1], filters, viewer, sponsoring
    )
    features: list[AtlasClusterFeature | AtlasEntryFeature] = []
    for cell in cells:
        if cell.members == 1:
            # Gone between the two reads (withdrawn, blocked): left out rather than guessed.
            if cell.only_id in singles:
                features.append(singles[cell.only_id])
            continue
        features.append(
            AtlasClusterFeature(
                geometry=_point(float(cell.mean_lat), float(cell.mean_lng)),
                properties=AtlasClusterProperties(
                    id=f"{zoom}:{cell.cell_x}:{cell.cell_y}",
                    count=cell.members,
                    bbox=[cell.west, cell.south, cell.east, cell.north],
                ),
            )
        )
    return AtlasClusterCollection(features=features, truncated=truncated)


async def _entries_page(
    db: AsyncSession,
    window: Window,
    centre: tuple[float, float],
    filters: Filters,
    cursor: cursors.Cursor | None,
    limit: int,
    viewer: User | None = None,
    *,
    sponsoring: bool = True,
) -> AtlasEntriesPage:
    """
    Return a page of the visible entries in a window, nearest the centre first, with their total.

    The distance, in degrees, is from the centre `(lat, lng)`, snapped to a 0.05 degree cell, to
    the entry's public point; ties break by id, so a cursor `(distance, id)` never skips or repeats an entry. The centre is
    used for these queries only: no distance is returned and nothing is kept.
    """
    # The position may be the viewer's own: it is snapped to a coarse cell before any use, so
    # that neither a log of the statement nor the distances in the cursors can give it away.
    snapped = approximate(centre[0], centre[1], ORPHAN_QUERY_CELL_M)
    here = func.ST_SetSRID(func.ST_MakePoint(snapped.lng, snapped.lat), 4326)
    # The nearest-neighbour operator, on the geometry the spatial index holds: it orders by
    # distance in degrees, which is near enough for a window and lets the index answer.
    distance = MapEntry.public_geom.op("<->", return_type=Float)(here)

    def inside(*columns: Any) -> Select[Any]:
        statement = _visible(_joined(*columns), filters, viewer, sponsoring=sponsoring)
        return statement.where(_envelopes(window))

    total = await db.scalar(inside(func.count(MapEntry.id)))
    statement = inside(MapEntry, Insight, User, distance.label("distance")).order_by(
        distance, MapEntry.id
    )
    if cursor is not None:
        if cursor.score is None:
            raise cursors.invalid()
        statement = statement.where(
            (distance > cursor.score) | ((distance == cursor.score) & (MapEntry.id > cursor.id))
        )
    rows = (await db.execute(statement.limit(limit + 1))).all()
    page = rows[:limit]
    sponsors = await _sponsors(db, [row[0].id for row in page], viewer, sponsoring)
    last = page[-1] if len(rows) > limit else None
    return AtlasEntriesPage(
        items=[
            _feature(entry, insight, author, sponsors.get(entry.id), sponsoring=sponsoring)
            for entry, insight, author, _ in page
        ],
        next_cursor=(
            None
            if last is None
            else cursors.encode(
                cursors.Cursor(at=_DISTANCE_CURSOR_AT, id=last[0].id, score=float(last[3]))
            )
        ),
        total=int(total or 0),
    )


@asynccontextmanager
async def _bounded(db: AsyncSession) -> AsyncIterator[None]:
    """Cut the statements of this transaction at `QUERY_TIMEOUT_MS`, and answer 503 when one is."""
    await db.execute(text(f"SET LOCAL statement_timeout = {int(QUERY_TIMEOUT_MS)}"))
    try:
        yield
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) != _QUERY_CANCELED:
            raise
        message = "The map took too long to answer; ask for a smaller window."
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, message, status_code=503) from error


async def clusters_in(
    db: AsyncSession,
    window: Window,
    filters: Filters,
    zoom: int,
    viewer: User | None = None,
    *,
    sponsoring: bool = True,
) -> AtlasClusterCollection:
    """Group the visible entries of a window (`_clusters`), within the time one query may take."""
    async with _bounded(db):
        return await _clusters(db, window, filters, zoom, viewer, sponsoring=sponsoring)


async def entries_page(
    db: AsyncSession,
    window: Window,
    centre: tuple[float, float],
    filters: Filters,
    cursor: cursors.Cursor | None,
    limit: int,
    viewer: User | None = None,
    *,
    sponsoring: bool = True,
) -> AtlasEntriesPage:
    """List the visible entries of a window by distance (`_entries_page`), within the time allowed."""
    async with _bounded(db):
        return await _entries_page(
            db, window, centre, filters, cursor, limit, viewer, sponsoring=sponsoring
        )


async def published_entry(db: AsyncSession, entry_id: int, viewer: User | None = None) -> MapEntry:
    """
    Return a published or orphaned entry, or 404; 410 once withdrawn, so the address says it was there.

    A held or removed entry, and one of an author a block stands between, answer 404 like one
    that never existed: an id grants nothing. An entry whose place was widened is shown without
    its author, so it does not need the author to have a handle, and a block against its author
    changes nothing about the answer (it would name the author); a block against its sponsor
    hides it. The id an entry had before it was widened answers 410.
    """
    entry = await db.get(MapEntry, entry_id)
    if entry is None:
        if await db.get(MapEntryRetiredId, entry_id) is not None:
            raise gone()
        raise not_found()
    if entry.status is MapEntryStatus.WITHDRAWN:
        raise gone()
    if entry.status not in {MapEntryStatus.PUBLISHED, MapEntryStatus.ORPHANED}:
        raise not_found()
    author = await db.get(User, entry.user_id)
    if (
        author is None
        or not author.is_active
        or author.deleted_at is not None
        or (author.handle is None and entry.widened_level is None)
    ):
        raise not_found()
    if viewer is not None and not await db.scalar(
        select(MapEntry.id)
        .join(User, User.id == MapEntry.user_id)
        .where(MapEntry.id == entry.id, _not_hidden_by_a_block(viewer))
    ):
        raise not_found()
    return entry


async def entry_detail(
    db: AsyncSession,
    entry_id: int,
    viewer: User | None = None,
    *,
    photos: PhotoStore,
    sponsoring: bool = True,
) -> AtlasEntryOut:
    """
    Return an entry's page: the insight by reference, its scripture from the store, the public point.

    The photo's public address comes only when the owner chose to show it with the entry and the
    copy exists now (v2 §19); the keys never leave the server.
    """
    entry = await published_entry(db, entry_id, viewer)
    insight = await db.get(Insight, entry.insight_id)
    author = await db.get(User, entry.user_id)
    location = public_location(entry)
    if insight is None or author is None or location is None:
        raise not_found()
    quran = (
        [(insight.quran_surah, insight.quran_ayah)]
        if insight.quran_surah and insight.quran_ayah
        else []
    )
    hadith = (
        [(insight.hadith_collection, insight.hadith_number)]
        if insight.hadith_collection and insight.hadith_number
        else []
    )
    evidence = await load_evidence(db, quran, hadith)
    # Only what rests on a text shown here is said here (the owner's own view applies the same rule).
    shown = {f"quran:{s}:{a}" for s, a in quran if (s, a) in evidence.quran} | {
        f"hadith:{c}:{n}" for c, n in hadith if (c, n) in evidence.hadith
    }
    step = visible_step(insight.small_step, shown) or {}
    # The post of the same insight names its author: an anonymous entry points to none.
    post_id = (
        None
        if entry.widened_level is not None
        else await db.scalar(
            select(Post.id)
            .join(InsightPublication, InsightPublication.id == Post.publication_id)
            .where(
                InsightPublication.insight_id == insight.id,
                Post.status == PostStatus.PUBLISHED,
                Post.visibility == PostVisibility.PUBLIC,
            )
            .order_by(Post.published_at.desc())
            .limit(1)
        )
    )
    sponsor = (await _sponsors(db, [entry.id], viewer, sponsoring)).get(entry.id)
    return AtlasEntryOut(
        id=entry.id,
        title=insight.title,
        glimpse=insight.glimpse,
        relation_type=insight.relation,
        explanation=explanation_excerpt(visible_parts(insight.explanation, shown)),
        step=str(step["text"]) if step.get("text") else None,
        concepts=list(insight.entity_ids or []),
        author=_shown_author(entry, author),
        orphaned=sponsoring and entry.status is MapEntryStatus.ORPHANED,
        sponsor=None if sponsor is None else sponsor.member,
        sponsor_reflection=None if sponsor is None else sponsor.reflection,
        sponsor_reflection_id=(
            None if sponsor is None or sponsor.reflection is None else sponsor.sponsorship_id
        ),
        location=location,
        place=place_of(entry),
        quran=[evidence.quran[key] for key in quran if key in evidence.quran],
        hadith=[evidence.hadith[key] for key in hadith if key in evidence.hadith],
        post_id=post_id,
        photo_url=(
            photo_service.public_url(photos, insight.photo_public_key) if entry.with_photo else None
        ),
        published_on=_published_on(entry),
    )


async def place_page(
    db: AsyncSession,
    geoname_id: int,
    cursor: cursors.Cursor | None,
    limit: int,
    viewer: User | None = None,
    *,
    sponsoring: bool = True,
) -> AtlasPlaceOut:
    """Return a place and the published entries labelled with it, newest first; 404 without any."""
    statement = _published_rows(Filters(), viewer, sponsoring=sponsoring).where(
        MapEntry.place_geoname_id == geoname_id
    )
    if cursor is not None:
        day = _published_day()
        statement = statement.where(
            (day < cursor.at) | ((day == cursor.at) & (MapEntry.id < cursor.id))
        )
    rows = (await db.execute(statement.limit(limit + 1))).all()
    geoname = await db.scalar(
        select(GeoName).where(GeoName.geoname_id == geoname_id, GeoName.is_active.is_(True))
    )
    if not rows or geoname is None or geoname.latitude is None or geoname.longitude is None:
        raise AppError(ErrorCode.NOT_FOUND, "No such place on the atlas.", status_code=404)
    first = rows[0][0]
    ref = place_of(first)
    if ref is None:
        raise AppError(ErrorCode.NOT_FOUND, "No such place on the atlas.", status_code=404)
    page = rows[:limit]
    last = page[-1][0] if len(rows) > limit else None
    sponsors = await _sponsors(db, [entry.id for entry, _, _ in page], viewer, sponsoring)
    return AtlasPlaceOut(
        place=ref,
        point=_point(float(geoname.latitude), float(geoname.longitude)),
        entries=[
            _feature(entry, insight, author, sponsors.get(entry.id), sponsoring=sponsoring)
            for entry, insight, author in page
        ],
        next_cursor=(
            None
            if last is None or last.published_at is None
            else cursors.encode(cursors.Cursor(at=_day_start(last), id=last.id))
        ),
    )


def _near(lat: float, lng: float, radius_m: float) -> ColumnElement[bool]:
    """Match the public points within `radius_m` metres of a position, by their widened place."""
    here = func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326)
    within = func.ST_DWithin(cast(MapEntry.public_geom, Geography), cast(here, Geography), radius_m)
    # The box lets the spatial index prune first; one that would pass a pole or the antimeridian
    # is skipped, since a plain expansion would miss what lies across it.
    margin = radius_m / (METERS_PER_DEGREE * max(math.cos(math.radians(lat)), _MIN_COSINE))
    if abs(lng) + margin > 180 or abs(lat) + margin > 90:
        return within
    return within & MapEntry.public_geom.op("&&")(func.ST_Expand(here, margin))


async def _area_of(db: AsyncSession, lat: float, lng: float) -> list[ColumnElement[bool]]:
    """
    Match the widened places the position lies in.

    A place widened to a region or a country is far from its own centre for most of the people
    who live there, so distance alone would not find it for them. The position's own city, region
    and country, from GeoNames, say which widened places it is inside of.
    """
    found = await geo_service.nearest_place(db, lat, lng)
    areas: list[ColumnElement[bool]] = []
    if found.place is not None:
        areas.append(
            (MapEntry.widened_level == WidenLevel.CITY)
            & (MapEntry.place_geoname_id == found.place.geoname_id)
        )
    if found.admin_area is not None:
        areas.append(
            (MapEntry.widened_level == WidenLevel.REGION)
            & (MapEntry.place_geoname_id == found.admin_area.geoname_id)
        )
    if found.country is not None:
        areas.append(
            (MapEntry.widened_level == WidenLevel.COUNTRY)
            & (MapEntry.country_iso2 == found.country.iso2)
        )
    return areas


async def orphans_near(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_m: float,
    cursor: cursors.Cursor | None,
    limit: int,
) -> AtlasOrphansOut:
    """
    Return the orphaned entries around a position, at their widened place only, newest first.

    The position is snapped to a grid of about 0.05 degrees before anything is asked, is used for
    this one query and is kept nowhere. An entry is near when its public point is within the
    radius or the position lies inside the area it was widened to. A block changes nothing here:
    an orphaned entry has no author to name, and hiding it from a blocker would name him.
    """
    snapped = approximate(lat, lng, ORPHAN_QUERY_CELL_M)
    near = or_(
        _near(snapped.lat, snapped.lng, radius_m), *await _area_of(db, snapped.lat, snapped.lng)
    )
    day = _published_day()
    statement = (
        select(MapEntry, Insight, User)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .join(User, User.id == MapEntry.user_id)
        .where(
            MapEntry.status == MapEntryStatus.ORPHANED,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            near,
        )
        .order_by(day.desc(), MapEntry.id.desc())
    )
    if cursor is not None:
        statement = statement.where(
            (day < cursor.at) | ((day == cursor.at) & (MapEntry.id < cursor.id))
        )
    rows = (await db.execute(statement.limit(limit + 1))).all()
    page = rows[:limit]
    last = page[-1][0] if len(rows) > limit else None
    return AtlasOrphansOut(
        features=[_feature(entry, insight, author) for entry, insight, author in page],
        next_cursor=None
        if last is None
        else cursors.encode(cursors.Cursor(at=_day_start(last), id=last.id)),
    )
