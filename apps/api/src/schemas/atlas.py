"""
Bodies of the atlas routes («أطلس بصائر العالم»).

Two families, kept apart on purpose. The owner's schemas (`CapturePointIn`, `MapEntryOwnerOut`)
carry the exact capture point, which only its owner ever receives. The public schemas
(`AtlasFeature`, `AtlasEntryOut`, `AtlasPlaceOut`) carry the published point alone, the centre of
the grid cell the capture point fell in, computed on the server. No public schema has a field for
a latitude, a longitude, an accuracy or a capture time: a test lists every field of every public
schema here, so adding one fails the build until it is justified.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.atlas import LocationMeaning, LocationSource, MapEntryStatus
from src.schemas.geo import GeoJsonPoint
from src.schemas.public_id import PublicId
from src.schemas.social import HadithEvidenceOut, MemberOut, QuranEvidenceOut

Latitude = Annotated[float, Field(ge=-90, le=90, description="Degrees; zero is a value")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="Degrees; zero is a value")]


class CapturePointIn(BaseModel):
    """Where the photo was taken, or the public place the owner chose; private to the owner."""

    model_config = ConfigDict(extra="forbid")

    latitude: Latitude
    longitude: Longitude
    accuracy_m: Annotated[int, Field(ge=0, le=100_000)] | None = None
    source: LocationSource
    meaning: LocationMeaning = LocationMeaning.CAPTURE_POINT
    captured_at: datetime | None = None
    measured_at: datetime | None = None


class CapturePointOut(BaseModel):
    """The owner's own point, echoed to the owner alone."""

    latitude: float
    longitude: float
    accuracy_m: int | None
    source: LocationSource
    captured_at: datetime | None
    measured_at: datetime | None
    confirmed_at: datetime


class GeoJsonPolygon(BaseModel):
    """A GeoJSON Polygon: one closed ring of [longitude, latitude] positions."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[Annotated[list[float], Field(min_length=2, max_length=2)]]]


class PlaceRef(BaseModel):
    """The populated place a public point is labelled with, from GeoNames."""

    geoname_id: int
    label: str
    admin_label: str | None
    country_iso2: str | None
    country_label: str | None


class PublicLocationOut(BaseModel):
    """What the map shows: the cell centre, how wide the cell is, and the words for it."""

    point: GeoJsonPoint
    cell_m: int
    precision_label: str
    meaning: LocationMeaning
    meaning_label: str


class PublicLocationPreview(PublicLocationOut):
    """The owner's preview before publishing: the cell itself, so they can see what is shown."""

    cell: GeoJsonPolygon


class MapEntryOwnerOut(BaseModel):
    """An entry as its owner sees it: the private point, the public preview, the state."""

    id: PublicId
    insight_id: PublicId
    title: str
    status: MapEntryStatus
    capture: CapturePointOut | None = Field(description="Null once the entry is withdrawn")
    public: PublicLocationPreview | None = Field(description="Null once the entry is withdrawn")
    place: PlaceRef | None
    published_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime


# ─── Public ───


class AtlasFeatureProperties(BaseModel):
    id: PublicId
    insight_id: PublicId
    title: str
    glimpse: str
    author: MemberOut
    place: PlaceRef | None
    cell_m: int
    precision_label: str
    published_at: datetime


class AtlasFeature(BaseModel):
    """One published entry as a GeoJSON Feature; `geometry` is the public point."""

    type: Literal["Feature"] = "Feature"
    id: PublicId
    geometry: GeoJsonPoint
    properties: AtlasFeatureProperties


class AtlasFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AtlasFeature]
    truncated: bool = Field(description="More entries lie in the window than were returned")


class AtlasEntryOut(BaseModel):
    """A published entry on its own page: the insight by reference, the public point, its place."""

    id: PublicId
    insight_id: PublicId
    title: str
    glimpse: str
    relation_type: str
    explanation: str = Field(description="The app's explanation, shortened; written by the app")
    step: str | None
    concepts: list[str]
    author: MemberOut
    location: PublicLocationOut
    place: PlaceRef | None
    quran: list[QuranEvidenceOut]
    hadith: list[HadithEvidenceOut]
    post_id: PublicId | None = Field(
        description="The public post of the same insight, if one is published"
    )
    published_at: datetime


class AtlasPlaceOut(BaseModel):
    """A place page: the place, its point from GeoNames, and the entries labelled with it."""

    place: PlaceRef
    point: GeoJsonPoint
    entries: list[AtlasFeature]
    next_cursor: str | None
