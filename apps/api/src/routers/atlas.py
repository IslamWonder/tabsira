"""
«أطلس بصائر العالم»: placing an insight on the map, and reading the map.

The owner's routes carry the exact point, to the owner alone. The public routes return the
published point only, computed on the server, and never a capture point, an accuracy or a
time of capture (extension §10). Everything sits behind the atlas feature.
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
    limited,
    requires,
)
from src.errors import ErrorCode
from src.features import FeatureFlag
from src.scans.deps import PublicIdPath
from src.schemas.atlas import (
    AtlasEntryOut,
    AtlasFeatureCollection,
    AtlasPlaceOut,
    CapturePointIn,
    MapEntryOwnerOut,
)
from src.services import atlas_service
from src.services import cursor as cursors
from src.services.atlas_service import Filters, Window
from src.services.social_limits import WriteKind

router = APIRouter(
    tags=["atlas"],
    dependencies=[Depends(requires(FeatureFlag.ATLAS, code=ErrorCode.FEATURE_DISABLED))],
)

Degrees = Annotated[float, Query(ge=-180, le=180)]
Latitude = Annotated[float, Query(ge=-90, le=90)]
Country = Annotated[str | None, Query(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")]
Concept = Annotated[str | None, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]
WindowLimit = Annotated[int, Query(ge=1, le=atlas_service.WINDOW_MAX)]
PageLimit = Annotated[int, Query(ge=1, le=atlas_service.PLACE_PAGE_MAX)]


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
    )
    return AtlasFeatureCollection(features=features, truncated=truncated)


@router.get("/atlas/entries/{entry_id}", summary="One published entry")
async def entry(
    entry_id: PublicIdPath, db: DbDep, viewer: OptionalUser, photos: PhotoStoreDep
) -> AtlasEntryOut:
    """Return the entry's page: the insight with its scripture from the store, the public point and its place; 410 once withdrawn."""
    return await atlas_service.entry_detail(db, entry_id, viewer, photos=photos)


@router.get("/atlas/places/{geoname_id}", summary="A place and the entries labelled with it")
async def place_entries(
    geoname_id: Annotated[int, Path(ge=1)],
    db: DbDep,
    viewer: OptionalUser,
    cursor: str | None = None,
    limit: PageLimit = atlas_service.PLACE_PAGE_DEFAULT,
) -> AtlasPlaceOut:
    """«ذاكرة المكان»: the place from GeoNames and its published entries, newest first; 404 without any."""
    return await atlas_service.place_page(db, geoname_id, cursors.decode(cursor), limit, viewer)
