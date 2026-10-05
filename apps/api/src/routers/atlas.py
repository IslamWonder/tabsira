"""
«أطلس بصائر العالم»: placing an insight on the map, and reading the map.

The owner's routes carry the exact point, to the owner alone. The public routes return the
published point only, computed on the server, and never a capture point, an accuracy or a
time of capture (extension §10). Everything sits behind the atlas feature; the sponsoring of
orphaned entries («كفالة بصيرة», decision 60) sits behind its own, which needs the atlas.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from src.deps import (
    CurrentUser,
    DbDep,
    OptionalUser,
    PhotoStoreDep,
    PublicMember,
    SettingsDep,
    TextGuardDep,
    limited,
    requires,
)
from src.errors import ErrorCode
from src.features import FeatureFlag
from src.scans.deps import PublicIdPath
from src.schemas.atlas import (
    AtlasClusterCollection,
    AtlasEntriesPage,
    AtlasEntryOut,
    AtlasFeatureCollection,
    AtlasOrphansOut,
    AtlasPlaceOut,
    CapturePointIn,
    MapEntryOwnerOut,
    SponsorshipOut,
    SponsorshipReflectionIn,
)
from src.services import atlas_service, sponsorship_service
from src.services import cursor as cursors
from src.services.atlas_service import Filters, Window
from src.services.social_limits import WriteKind

router = APIRouter(
    tags=["atlas"],
    dependencies=[Depends(requires(FeatureFlag.ATLAS, code=ErrorCode.FEATURE_DISABLED))],
)

sponsoring = Depends(requires(FeatureFlag.ATLAS_SPONSORSHIP))

Degrees = Annotated[float, Query(ge=-180, le=180)]
Latitude = Annotated[float, Query(ge=-90, le=90)]
Country = Annotated[str | None, Query(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")]
Concept = Annotated[str | None, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]
WindowLimit = Annotated[int, Query(ge=1, le=atlas_service.WINDOW_MAX)]
Zoom = Annotated[int, Query(ge=0, le=22, description="Map zoom level")]
PageLimit = Annotated[int, Query(ge=1, le=atlas_service.PLACE_PAGE_MAX)]
Radius = Annotated[
    float,
    Query(
        ge=atlas_service.ORPHAN_RADIUS_MIN_M,
        le=atlas_service.ORPHAN_RADIUS_MAX_M,
        description="Metres",
    ),
]


@router.put(
    "/insights/{insight_id}/map",
    summary="Place one of the caller's insights on the atlas, as a draft",
    dependencies=[limited(WriteKind.POST)],
)
async def place_insight(
    insight_id: PublicIdPath,
    body: CapturePointIn,
    user: PublicMember,
    db: DbDep,
    settings: SettingsDep,
    photos: PhotoStoreDep,
) -> MapEntryOwnerOut:
    """
    Keep the exact point privately and answer with what the map will show.

    The public point is the centre of the grid cell (GEO_APPROX_CELL_METERS), labelled with
    the nearest populated place; the answer carries the cell as a polygon, so the owner reviews
    it before publishing. 409 INSIGHT_NOT_PUBLISHABLE for an insight that is not the pipeline's.
    Placing a published entry again takes it off the map, and its photo's public copy with it.
    """
    result = await atlas_service.place(db, settings, user, insight_id, body, photos=photos)
    await db.commit()
    return result


@router.get("/insights/{insight_id}/map", summary="The caller's own entry for an insight")
async def my_entry(insight_id: PublicIdPath, user: CurrentUser, db: DbDep) -> MapEntryOwnerOut:
    """Return the entry with its private point and its public preview; 404 when there is none."""
    return await atlas_service.mine(db, user, insight_id)


@router.post(
    "/insights/{insight_id}/map/publish",
    summary="Show the entry on the atlas",
    dependencies=[limited(WriteKind.POST)],
)
async def publish_entry(
    insight_id: PublicIdPath, user: PublicMember, db: DbDep, photos: PhotoStoreDep
) -> MapEntryOwnerOut:
    """Publish a placed draft; 409 for an entry that is not a draft."""
    result = await atlas_service.publish(db, user, insight_id, photos=photos)
    await db.commit()
    return result


@router.delete(
    "/insights/{insight_id}/map",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw the entry from the atlas",
    dependencies=[limited(WriteKind.POST)],
)
async def withdraw_entry(
    insight_id: PublicIdPath, user: CurrentUser, db: DbDep, photos: PhotoStoreDep
) -> Response:
    """Take the entry off the map and forget its exact point; its address answers 410 from then on."""
    await atlas_service.withdraw(db, user, insight_id, photos=photos)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/map-entries", summary="The caller's entries, in every state")
async def my_entries(user: CurrentUser, db: DbDep) -> list[MapEntryOwnerOut]:
    return await atlas_service.list_mine(db, user)


@router.get("/atlas/entries", summary="The published entries inside a map window")
async def entries_in_window(
    db: DbDep,
    settings: SettingsDep,
    viewer: OptionalUser,
    west: Degrees,
    south: Latitude,
    east: Degrees,
    north: Latitude,
    since: date | None = None,
    country: Country = None,
    concept: Concept = None,
    limit: WindowLimit = atlas_service.WINDOW_DEFAULT,
) -> AtlasFeatureCollection:
    """
    Return a GeoJSON FeatureCollection of the published entries in the window, newest first.

    Every geometry is a public point: the centre of an approximation cell, never where a photo
    was taken, and `published_on` is a day, never a time. A window with `west > east` crosses
    the antimeridian. `truncated` says more entries lie in the window than `limit` allowed; ask
    for a smaller window. For a signed-in viewer, entries of members a block stands between
    are left out.
    """
    features, truncated = await atlas_service.features_in(
        db,
        Window(west=west, south=south, east=east, north=north),
        Filters(since=since, country=country, concept=concept),
        limit,
        viewer,
        sponsoring=settings.is_enabled(FeatureFlag.ATLAS_SPONSORSHIP),
    )
    return AtlasFeatureCollection(features=features, truncated=truncated)


@router.get("/atlas/clusters", summary="The published entries of a map window, grouped")
async def clusters_in_window(
    db: DbDep,
    settings: SettingsDep,
    viewer: OptionalUser,
    west: Degrees,
    south: Latitude,
    east: Degrees,
    north: Latitude,
    zoom: Zoom,
    since: date | None = None,
    country: Country = None,
    concept: Concept = None,
) -> AtlasClusterCollection:
    """
    Return groups and single entries of the window, whatever the number of entries.

    Each `properties.kind` is `cluster` (a `count` of visible entries, the `bbox` of their public
    points, a stable `id` of the grid cell, a point at the mean of the public points) or `entry`
    (one entry, as in `/atlas/entries`). A grid cell is about 60 CSS pixels at the zoom; from
    zoom 16 nothing is grouped. At most 500 features come back; `truncated` says there were more.
    Counts leave out the entries a block hides from a signed-in viewer.
    """
    return await atlas_service.clusters_in(
        db,
        Window(west=west, south=south, east=east, north=north),
        Filters(since=since, country=country, concept=concept),
        zoom,
        viewer,
        sponsoring=settings.is_enabled(FeatureFlag.ATLAS_SPONSORSHIP),
    )


@router.get("/atlas/entries/page", summary="The entries of a map window, nearest the centre first")
async def entries_page(
    db: DbDep,
    settings: SettingsDep,
    viewer: OptionalUser,
    west: Degrees,
    south: Latitude,
    east: Degrees,
    north: Latitude,
    center_lat: Latitude,
    center_lng: Degrees,
    since: date | None = None,
    country: Country = None,
    concept: Concept = None,
    cursor: str | None = None,
    limit: PageLimit = atlas_service.PLACE_PAGE_DEFAULT,
) -> AtlasEntriesPage:
    """
    Return one page of the window's visible entries by distance from the map's centre, and the total.

    `total` counts every visible entry of the window, not the page. Ask for the next page with the
    same window and centre and the `next_cursor`. The centre is snapped to a 0.05 degree cell
    before it is used, for this request only; no distance is returned. Entries of members a block stands between are left out.
    """
    return await atlas_service.entries_page(
        db,
        Window(west=west, south=south, east=east, north=north),
        (center_lat, center_lng),
        Filters(since=since, country=country, concept=concept),
        cursors.decode(cursor),
        limit,
        viewer,
        sponsoring=settings.is_enabled(FeatureFlag.ATLAS_SPONSORSHIP),
    )


@router.get("/atlas/entries/{entry_id}", summary="One published entry")
async def entry(
    entry_id: PublicIdPath,
    db: DbDep,
    settings: SettingsDep,
    viewer: OptionalUser,
    photos: PhotoStoreDep,
) -> AtlasEntryOut:
    """
    Return the entry's page: the insight with its scripture from the store, the public point and its place.

    410 once withdrawn, and for the id an entry had before its place was widened.
    """
    return await atlas_service.entry_detail(
        db,
        entry_id,
        viewer,
        photos=photos,
        sponsoring=settings.is_enabled(FeatureFlag.ATLAS_SPONSORSHIP),
    )


@router.get("/atlas/places/{geoname_id}", summary="A place and the entries labelled with it")
async def place_entries(
    geoname_id: Annotated[int, Path(ge=1)],
    db: DbDep,
    settings: SettingsDep,
    viewer: OptionalUser,
    cursor: str | None = None,
    limit: PageLimit = atlas_service.PLACE_PAGE_DEFAULT,
) -> AtlasPlaceOut:
    """«ذاكرة المكان»: the place from GeoNames and its published entries, newest first; 404 without any."""
    return await atlas_service.place_page(
        db,
        geoname_id,
        cursors.decode(cursor),
        limit,
        viewer,
        sponsoring=settings.is_enabled(FeatureFlag.ATLAS_SPONSORSHIP),
    )


# ─── «كفالة بصيرة»: orphaned entries and their sponsors (decision 60) ───


@router.get(
    "/atlas/orphans",
    summary="Orphaned entries near a point, at their widened place",
    dependencies=[sponsoring],
)
async def orphans_near(
    db: DbDep,
    lat: Latitude,
    lng: Degrees,
    radius: Radius = atlas_service.ORPHAN_RADIUS_DEFAULT_M,
    cursor: str | None = None,
    limit: PageLimit = atlas_service.PLACE_PAGE_DEFAULT,
) -> AtlasOrphansOut:
    """
    Entries nobody looks after near the position, newest first.

    Near means the entry's public point is within `radius` metres, or the position lies inside the
    city, region or country the place was widened to. Each is shown at the place it was widened
    to, with no author's name. The position is snapped to a grid of about 0.05 degrees before
    anything is asked, used for this request and kept nowhere; the answer is never cached. A block
    changes nothing here: the author is anonymous.
    """
    return await atlas_service.orphans_near(db, lat, lng, radius, cursors.decode(cursor), limit)


@router.put(
    "/atlas/entries/{entry_id}/sponsorship",
    summary="Sponsor an orphaned entry",
    dependencies=[sponsoring, limited(WriteKind.POST)],
)
async def sponsor_entry(entry_id: PublicIdPath, user: PublicMember, db: DbDep) -> SponsorshipOut:
    """
    Look after an orphaned entry: it returns to the atlas at its widened place, under the caller's handle.

    404 for an entry the caller cannot see (a block against its sponsor; a block against its
    anonymous author changes nothing), 409 for their own entry, one that has a sponsor or one that
    is not orphaned, and
    `UNDER_13_CANNOT_PUBLISH` for an account that declared it is under 13. One sponsor at a time.
    """
    await sponsorship_service.start(db, user, entry_id)
    await db.commit()
    return _mine(await sponsorship_service.list_mine(db, user), entry_id)


@router.delete(
    "/atlas/entries/{entry_id}/sponsorship",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the caller's sponsorship",
    dependencies=[sponsoring, limited(WriteKind.POST)],
)
async def end_sponsorship(entry_id: PublicIdPath, user: CurrentUser, db: DbDep) -> Response:
    """Stop looking after the entry; the reflection goes with it and the entry stays on the atlas for now."""
    await sponsorship_service.end(db, user, entry_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/atlas/entries/{entry_id}/sponsorship/reflection",
    summary="Write or replace the sponsor's reflection",
    dependencies=[sponsoring, limited(WriteKind.COMMENT)],
)
async def write_reflection(
    entry_id: PublicIdPath,
    body: SponsorshipReflectionIn,
    user: PublicMember,
    db: DbDep,
    guard: TextGuardDep,
) -> SponsorshipOut:
    """
    Put the sponsor's own words under the entry; the guard judges them as it judges a comment.

    The answer says what it decided: `published`, `rejected` with its reason, or `pending_review`
    while a person looks, and until it is published only its sponsor sees it. 422 for words that
    read like Quran or hadith, 404 without an open sponsorship of the caller's.
    """
    await sponsorship_service.write_reflection(db, user, entry_id, body.reflection, guard)
    await db.commit()
    return _mine(await sponsorship_service.list_mine(db, user), entry_id)


@router.get(
    "/me/sponsorships",
    summary="The caller's sponsorships, with the state of their reflections",
    dependencies=[sponsoring],
)
async def my_sponsorships(user: CurrentUser, db: DbDep) -> list[SponsorshipOut]:
    return await sponsorship_service.list_mine(db, user)


def _mine(sponsorships: list[SponsorshipOut], entry_id: int) -> SponsorshipOut:
    """Pick the open sponsorship of the entry out of the caller's own."""
    return next(item for item in sponsorships if item.entry_id == entry_id and item.active)
