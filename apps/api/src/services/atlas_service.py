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
from datetime import datetime

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
from src.models.scan import Insight
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
from src.services import geo_service
from src.services.evidence_view import load_evidence
from src.services.insight_table_source import PUBLISHABLE_ENGINE, explanation_excerpt

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
    since: datetime | None = None
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


async def _own_entry(db: AsyncSession, user: User, insight_id: int) -> tuple[MapEntry, Insight]:
    insight = await _own_insight(db, user, insight_id)
    entry = await db.scalar(select(MapEntry).where(MapEntry.insight_id == insight.id))
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
    if insight.engine != PUBLISHABLE_ENGINE:
        message = "Only an insight of the real pipeline can be placed on the atlas."
        raise AppError(ErrorCode.INSIGHT_NOT_PUBLISHABLE, message, status_code=409)
    cell_m = int(settings.geo_approx_cell_meters)
    centre = approximate(body.latitude, body.longitude, cell_m)
    labels = await _label(db, centre.lat, centre.lng)
    entry = await db.scalar(select(MapEntry).where(MapEntry.insight_id == insight.id))
    if entry is None:
        entry = MapEntry(user_id=user.id, insight_id=insight.id, cell_m=cell_m)
        db.add(entry)
    entry.public_lat = centre.lat
    entry.public_lng = centre.lng
    entry.public_geom = WKTElement(f"POINT({centre.lng} {centre.lat})", srid=4326)
    entry.cell_m = cell_m
    entry.location_meaning = body.meaning
    for column, value in labels.items():
        setattr(entry, column, value)
    entry.status = MapEntryStatus.DRAFT
    entry.published_at = None
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


async def publish(db: AsyncSession, user: User, insight_id: int) -> MapEntryOwnerOut:
    """Show the entry on the atlas; a draft with a point only."""
    entry, insight = await _own_entry(db, user, insight_id)
    if entry.status is not MapEntryStatus.DRAFT or entry.public_lat is None:
        message = "Only a placed draft can be published."
        raise _wrong_state(message)
    entry.status = MapEntryStatus.PUBLISHED
    entry.published_at = clock.utcnow()
    await db.flush()
    return owner_view(entry, insight, await db.get(MapCapturePoint, entry.id))


async def withdraw(db: AsyncSession, user: User, insight_id: int) -> None:
    """
    Take the entry off the atlas and forget the exact point.

    The public point is cleared too: nothing of the location survives but the tombstone that
    makes the entry's address answer 410.
    """
    entry, _ = await _own_entry(db, user, insight_id)
    if entry.status is MapEntryStatus.WITHDRAWN:
        return
    point = await db.get(MapCapturePoint, entry.id)
    if point is not None:
        await db.delete(point)
    entry.status = MapEntryStatus.WITHDRAWN
    entry.withdrawn_at = clock.utcnow()
    entry.public_lat = None
    entry.public_lng = None
    entry.public_geom = None
    await db.flush()


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


def _feature(entry: MapEntry, insight: Insight, author: User) -> AtlasFeature:
    # A published entry always has its point (a database constraint); the checks keep mypy honest.
    lat = entry.public_lat if entry.public_lat is not None else 0.0
    lng = entry.public_lng if entry.public_lng is not None else 0.0
    published_at = entry.published_at if entry.published_at is not None else entry.created_at
    return AtlasFeature(
        id=entry.id,
        geometry=_point(lat, lng),
        properties=AtlasFeatureProperties(
            id=entry.id,
            insight_id=entry.insight_id,
            title=insight.title,
            glimpse=insight.glimpse,
            author=_author(author),
            place=_place_of(entry),
            cell_m=entry.cell_m,
            precision_label=precision_label(entry.cell_m),
            published_at=published_at,
        ),
    )


def _published_rows(filters: Filters):  # type: ignore[no-untyped-def]
    statement = (
        select(MapEntry, Insight, User)
        .join(Insight, Insight.id == MapEntry.insight_id)
        .join(User, User.id == MapEntry.user_id)
        .where(MapEntry.status == MapEntryStatus.PUBLISHED, *_visible_author())
    )
    if filters.since is not None:
        statement = statement.where(MapEntry.published_at >= filters.since)
    if filters.country is not None:
        statement = statement.where(MapEntry.country_iso2 == filters.country.upper())
    if filters.concept is not None:
        statement = statement.where(Insight.entity_ids.contains([filters.concept]))
    return statement.order_by(MapEntry.published_at.desc(), MapEntry.id.desc())


async def features_in(
    db: AsyncSession, window: Window, filters: Filters, limit: int
) -> tuple[list[AtlasFeature], bool]:
    """Return the published entries inside the window, newest first, and whether more were left out."""
    rows = (
        await db.execute(_published_rows(filters).where(_envelopes(window)).limit(limit + 1))
    ).all()
    features = [_feature(entry, insight, author) for entry, insight, author in rows[:limit]]
    return features, len(rows) > limit


async def published_entry(db: AsyncSession, entry_id: int) -> MapEntry:
    """Return a published entry, or 404; 410 once withdrawn, so the address says it was there."""
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
    return entry


async def entry_detail(db: AsyncSession, entry_id: int) -> AtlasEntryOut:
    """Return an entry's page: the insight by reference, its scripture from the store, the public point."""
    entry = await published_entry(db, entry_id)
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
    step = insight.small_step or {}
    return AtlasEntryOut(
        id=entry.id,
        insight_id=insight.id,
        title=insight.title,
        glimpse=insight.glimpse,
        relation_type=insight.relation,
        explanation=explanation_excerpt(insight.explanation),
        step=str(step["text"]) if step.get("text") else None,
        concepts=list(insight.entity_ids or []),
        author=_author(author),
        location=location,
        place=_place_of(entry),
        quran=[evidence.quran[key] for key in quran if key in evidence.quran],
        hadith=[evidence.hadith[key] for key in hadith if key in evidence.hadith],
        post_id=post_id,
        published_at=entry.published_at if entry.published_at is not None else entry.created_at,
    )


async def place_page(
    db: AsyncSession, geoname_id: int, cursor: cursors.Cursor | None, limit: int
) -> AtlasPlaceOut:
    """Return a place and the published entries labelled with it, newest first; 404 without any."""
    statement = _published_rows(Filters()).where(MapEntry.place_geoname_id == geoname_id)
    if cursor is not None:
        statement = statement.where(
            (MapEntry.published_at < cursor.at)
            | ((MapEntry.published_at == cursor.at) & (MapEntry.id < cursor.id))
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
            else cursors.encode(cursors.Cursor(at=last.published_at, id=last.id))
        ),
    )
