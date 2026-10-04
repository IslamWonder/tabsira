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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from src import clock
from src.config import Settings
from src.errors import AppError, ErrorCode
from src.geo.privacy import approximate, cell_polygon
from src.messages import messages_for
from src.models.atlas import LocationMeaning, MapCapturePoint, MapEntry, MapEntryStatus
from src.models.geonames import GeoName
from src.models.scan import Insight, Scan
from src.models.social import InsightPublication, Post, PostStatus, PostVisibility
from src.models.user import User
from src.schemas.atlas import (
    AtlasEntryOut,
    AtlasFeature,
    AtlasFeatureProperties,
    AtlasPlaceOut,
    CapturePointIn,
    CapturePointOut,
    GeoJsonPolygon,
    MapEntryOwnerOut,
    PlaceRef,
    PublicLocationOut,
    PublicLocationPreview,
)
from src.schemas.geo import GeoJsonPoint
from src.schemas.social import MemberOut
from src.services import cursor as cursors
from src.services import geo_service, photo_service, publication_service
from src.services.block_service import blocked_with
from src.services.evidence_view import load_evidence
from src.services.insight_table_source import explanation_excerpt, snapshot_of
from src.services.insight_view import visible_parts, visible_step
from src.services.post_view import outcome_message
from src.storage.photos import PhotoStore

# Entries returned for one map window at most; the client asks again for a smaller window.
WINDOW_DEFAULT = 300
WINDOW_MAX = 1000
PLACE_PAGE_DEFAULT = 20
PLACE_PAGE_MAX = 50


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


def precision_label(cell_m: int) -> str:
    return messages_for().atlas_precision.format(metres=cell_m)


def meaning_label(meaning: LocationMeaning) -> str:
    return messages_for().atlas_meanings[meaning.value]


def _point(lat: float, lng: float) -> GeoJsonPoint:
    return GeoJsonPoint(coordinates=[lng, lat])


def _place_of(entry: MapEntry) -> PlaceRef | None:
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
        precision_label=precision_label(entry.cell_m),
        meaning=entry.location_meaning,
        meaning_label=meaning_label(entry.location_meaning),
    )


def _author(user: User) -> MemberOut:
    return MemberOut(handle=user.handle or "", public_name=user.public_name or "")


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
    db: AsyncSession, settings: Settings, user: User, insight_id: int, body: CapturePointIn
) -> MapEntryOwnerOut:
    """
    Keep the owner's exact point privately and compute what the map will show.

    The entry is a draft until the owner publishes it; placing a published entry again
    makes it a draft again, since what is shown changed. The cell size is the setting's at
    the time of placing, kept with the entry.
    """
    insight = await _own_insight(db, user, insight_id)
    await _check_publishable(db, insight)
    cell_m = int(settings.geo_approx_cell_meters)
    centre = approximate(body.latitude, body.longitude, cell_m)
    labels = await _label(db, centre.lat, centre.lng)
    entry = await db.scalar(select(MapEntry).where(_live(insight.id)))
    decided = {MapEntryStatus.PENDING_REVIEW, MapEntryStatus.REMOVED}
    if entry is not None and entry.status in decided:
        message = "A moderator's decision stands on this entry; it cannot be placed again."
        raise _wrong_state(message)
    if entry is None:
        # A withdrawn tombstone may stand beside it: the new entry takes a new address.
        entry = MapEntry(user_id=user.id, insight_id=insight.id, cell_m=cell_m)
        db.add(entry)
    entry.public_lat = centre.lat
    entry.public_lng = centre.lng
    entry.public_geom = WKTElement(f"POINT({centre.lng} {centre.lat})", srid=4326)
    entry.cell_m = cell_m
    entry.location_meaning = body.meaning
    entry.with_photo = body.photo
    for column, value in labels.items():
        setattr(entry, column, value)
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
    return owner_view(entry, insight, point)


def owner_view(
    entry: MapEntry, insight: Insight, point: MapCapturePoint | None
) -> MapEntryOwnerOut:
    public = public_location(entry)
    preview = None
    if public is not None and point is not None:
        polygon = cell_polygon(point.latitude, point.longitude, entry.cell_m)
        preview = PublicLocationPreview(
            **public.model_dump(),
            cell=GeoJsonPolygon(coordinates=polygon["coordinates"]),
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
        place=_place_of(entry),
        photo=entry.with_photo,
        published_at=entry.published_at,
        withdrawn_at=entry.withdrawn_at,
        created_at=entry.created_at,
    )


async def mine(db: AsyncSession, user: User, insight_id: int) -> MapEntryOwnerOut:
    entry, insight = await _own_entry(db, user, insight_id)
    return owner_view(entry, insight, await db.get(MapCapturePoint, entry.id))


async def list_mine(db: AsyncSession, user: User) -> list[MapEntryOwnerOut]:
    rows = await db.execute(
        select(MapEntry, Insight, MapCapturePoint)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .outerjoin(MapCapturePoint, MapCapturePoint.entry_id == MapEntry.id)
        .where(MapEntry.user_id == user.id)
        .order_by(MapEntry.created_at.desc(), MapEntry.id.desc())
    )
    return [owner_view(entry, insight, point) for entry, insight, point in rows]


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
    _clear_public_side(entry)
    await db.flush()
    if entry.with_photo:
        await photo_service.sync_public_copy(db, photos, insight.id)


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


def _feature(entry: MapEntry, insight: Insight, author: User) -> AtlasFeature:
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
            author=_author(author),
            place=_place_of(entry),
            cell_m=entry.cell_m,
            precision_label=precision_label(entry.cell_m),
            published_on=_published_on(entry),
        ),
    )


def _published_rows(filters: Filters, viewer: User | None):  # type: ignore[no-untyped-def]
    statement = (
        select(MapEntry, Insight, User)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .join(User, User.id == MapEntry.user_id)
        .where(MapEntry.status == MapEntryStatus.PUBLISHED, *_visible_author())
    )
    if viewer is not None:
        # A block hides each of the two from the other here as everywhere.
        statement = statement.where(User.id.not_in(blocked_with(viewer.id)))
    if filters.since is not None:
        statement = statement.where(
            MapEntry.published_at >= datetime.combine(filters.since, time.min, tzinfo=UTC)
        )
    if filters.country is not None:
        statement = statement.where(MapEntry.country_iso2 == filters.country.upper())
    if filters.concept is not None:
        statement = statement.where(Insight.entity_ids.contains([filters.concept]))
    return statement.order_by(_published_day().desc(), MapEntry.id.desc())


async def features_in(
    db: AsyncSession, window: Window, filters: Filters, limit: int, viewer: User | None = None
) -> tuple[list[AtlasFeature], bool]:
    """Return the published entries inside the window, newest first, and whether more were left out."""
    rows = (
        await db.execute(
            _published_rows(filters, viewer).where(_envelopes(window)).limit(limit + 1)
        )
    ).all()
    features = [_feature(entry, insight, author) for entry, insight, author in rows[:limit]]
    return features, len(rows) > limit


async def published_entry(db: AsyncSession, entry_id: int, viewer: User | None = None) -> MapEntry:
    """
    Return a published entry, or 404; 410 once withdrawn, so the address says it was there.

    A held or removed entry, and one of an author a block stands between, answer 404 like one
    that never existed: an id grants nothing.
    """
    entry = await db.get(MapEntry, entry_id)
    if entry is None:
        raise not_found()
    if entry.status is MapEntryStatus.WITHDRAWN:
        raise gone()
    if entry.status is not MapEntryStatus.PUBLISHED:
        raise not_found()
    author = await db.get(User, entry.user_id)
    if (
        author is None
        or not author.is_active
        or author.deleted_at is not None
        or author.handle is None
    ):
        raise not_found()
    if viewer is not None and await db.scalar(
        select(User.id).where(User.id == author.id, User.id.in_(blocked_with(viewer.id)))
    ):
        raise not_found()
    return entry


async def entry_detail(
    db: AsyncSession, entry_id: int, viewer: User | None = None, *, photos: PhotoStore
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
    post_id = await db.scalar(
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
    return AtlasEntryOut(
        id=entry.id,
        title=insight.title,
        glimpse=insight.glimpse,
        relation_type=insight.relation,
        explanation=explanation_excerpt(visible_parts(insight.explanation, shown)),
        step=str(step["text"]) if step.get("text") else None,
        concepts=list(insight.entity_ids or []),
        author=_author(author),
        location=location,
        place=_place_of(entry),
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
) -> AtlasPlaceOut:
    """Return a place and the published entries labelled with it, newest first; 404 without any."""
    statement = _published_rows(Filters(), viewer).where(MapEntry.place_geoname_id == geoname_id)
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
    ref = _place_of(first)
    if ref is None:
        raise AppError(ErrorCode.NOT_FOUND, "No such place on the atlas.", status_code=404)
    page = rows[:limit]
    last = page[-1][0] if len(rows) > limit else None
    return AtlasPlaceOut(
        place=ref,
        point=_point(float(geoname.latitude), float(geoname.longitude)),
        entries=[_feature(entry, insight, author) for entry, insight, author in page],
        next_cursor=(
            None
            if last is None or last.published_at is None
            else cursors.encode(cursors.Cursor(at=_day_start(last), id=last.id))
        ),
    )
