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

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.atlas import (
    SPONSOR_REFLECTION_MAX,
    LocationMeaning,
    LocationSource,
    MapEntryStatus,
    WidenLevel,
)
from src.models.social import CommentStatus
from src.schemas.geo import GeoJsonPoint
from src.schemas.public_id import PublicId
from src.schemas.social import HadithEvidenceOut, MemberOut, QuranEvidenceOut, clean_text

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
    photo: bool = Field(
        default=False,
        description="Show the insight's kept photo with the entry; nothing without a kept "
        "photo and the owner's photo consent (v2 §19)",
    )


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
    widened_level: WidenLevel | None = Field(
        default=None,
        description="Set once the place was widened to a city, a region or a country (decision 60): "
        "the point is then that area's centre, and it is never narrowed again",
    )


class PublicLocationPreview(PublicLocationOut):
    """The owner's preview before publishing: the cell itself, so they can see what is shown."""

    cell: GeoJsonPolygon | None = Field(
        default=None, description="Null once the place was widened: there is no cell any more"
    )


class WidenedOut(BaseModel):
    """What the owner is told about the widening of their entry's place (never the earlier cell)."""

    level: WidenLevel
    label: str | None
    at: datetime


class MapEntryOwnerOut(BaseModel):
    """An entry as its owner sees it: the private point, the public preview, the state."""

    id: PublicId
    insight_id: PublicId
    title: str
    status: MapEntryStatus
    status_message: str | None = Field(description="What happened to it, in Arabic, for its owner")
    capture: CapturePointOut | None = Field(description="Null once the entry is withdrawn")
    public: PublicLocationPreview | None = Field(description="Null once the entry is withdrawn")
    place: PlaceRef | None
    photo: bool = Field(description="The owner chose to show the insight's photo with it")
    sponsor: MemberOut | None = Field(
        default=None,
        description="Who looks after the entry now, when it is sponsored (decision 60)",
    )
    widened: WidenedOut | None = Field(
        default=None,
        description="When and to what level the entry's public place was widened, if it was",
    )
    published_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime


# ─── Public ───


class AtlasFeatureProperties(BaseModel):
    """No insight id here: a public id is a timestamp, and the scan time is nobody's business."""

    id: PublicId
    title: str
    glimpse: str
    author: MemberOut | None = Field(
        description="Null once the entry was orphaned: a widened place carries no author's name"
    )
    place: PlaceRef | None
    cell_m: int
    precision_label: str
    published_on: date = Field(description="The day, never the time: no trail of a person's hours")
    orphaned: bool = Field(
        default=False, description="Nobody looks after it: it can be sponsored (decision 60)"
    )
    widened_level: WidenLevel | None = None
    sponsor: MemberOut | None = Field(
        default=None, description="Who looks after it; chosen in public by the sponsor"
    )


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


class AtlasEntryProperties(AtlasFeatureProperties):
    """A single entry among clusters: the entry's own properties, told apart by `kind`."""

    kind: Literal["entry"] = "entry"


class AtlasEntryFeature(BaseModel):
    """A lone entry of the cluster answer, a point on the map like any other."""

    type: Literal["Feature"] = "Feature"
    id: PublicId
    geometry: GeoJsonPoint
    properties: AtlasEntryProperties


class AtlasClusterProperties(BaseModel):
    """
    What a group of entries says: how many, and where they lie. Never an id, an author or a time.

    The count is of the entries this viewer may see, and the box is the box of their public points.
    """

    kind: Literal["cluster"] = "cluster"
    id: str = Field(description="Stable for a grid cell at a zoom; not an entry id")
    count: int = Field(
        ge=2, description="Visible entries in the group, after the filters and blocks"
    )
    bbox: list[float] = Field(
        min_length=4,
        max_length=4,
        description="West, south, east, north of the members' public points, to zoom to the group",
    )


class AtlasClusterFeature(BaseModel):
    """A group of entries as a GeoJSON Feature; `geometry` is the mean of their public points."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJsonPoint
    properties: AtlasClusterProperties


class AtlasClusterCollection(BaseModel):
    """Groups and single entries of a window, told apart by `properties.kind`; bounded in size."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AtlasClusterFeature | AtlasEntryFeature]
    truncated: bool = Field(description="More groups lie in the window than were returned")


class AtlasEntryOut(BaseModel):
    """A published entry on its own page: the insight by reference, the public point, its place."""

    id: PublicId
    title: str
    glimpse: str
    relation_type: str
    explanation: str = Field(description="The app's explanation, shortened; written by the app")
    step: str | None
    concepts: list[str]
    author: MemberOut | None = Field(
        description="Null once the entry was orphaned, and for good after it: no handle beside a widened place"
    )
    orphaned: bool = Field(
        default=False, description="Nobody looks after it: any verified member may sponsor it"
    )
    sponsor: MemberOut | None = Field(
        default=None, description="Who looks after it; the sponsor chose to be named"
    )
    sponsor_reflection: str | None = Field(
        default=None,
        description="The sponsor's own words, once published; never scripture, never the author's",
    )
    sponsor_reflection_id: PublicId | None = Field(
        default=None,
        description="The id to report the reflection by (`target_type` sponsorship); null without one",
    )
    location: PublicLocationOut
    place: PlaceRef | None
    quran: list[QuranEvidenceOut]
    hadith: list[HadithEvidenceOut]
    post_id: PublicId | None = Field(
        description="The public post of the same insight, if one is published"
    )
    photo_url: str | None = Field(
        description="The address of the photo's public copy, only when the owner chose to show "
        "it with the entry and the copy exists; null otherwise. Never a storage key."
    )
    published_on: date


class AtlasPlaceOut(BaseModel):
    """A place page: the place, its point from GeoNames, and the entries labelled with it."""

    place: PlaceRef
    point: GeoJsonPoint
    entries: list[AtlasFeature]
    next_cursor: str | None


class AtlasOrphansOut(BaseModel):
    """Orphaned entries near a point, each at its widened place, newest first."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AtlasFeature]
    next_cursor: str | None


# ─── Sponsoring («كفالة بصيرة») ───


class SponsorshipReflectionIn(BaseModel):
    """The sponsor's own words under the entry: one, replaced by the next."""

    model_config = ConfigDict(extra="forbid")

    reflection: Annotated[str, Field(max_length=SPONSOR_REFLECTION_MAX * 2)]

    @field_validator("reflection")
    @classmethod
    def _reflection(cls, value: str) -> str:
        cleaned = clean_text(value, SPONSOR_REFLECTION_MAX)
        if cleaned is None:
            message = "must not be empty"
            raise ValueError(message)
        return cleaned


class SponsorshipOut(BaseModel):
    """One of the caller's sponsorships, with the state of their own reflection."""

    entry_id: PublicId
    title: str
    place: PlaceRef | None
    widened_level: WidenLevel | None
    id: PublicId = Field(description="The sponsorship's id: what a report of its reflection names")
    active: bool = Field(
        description="Always true: a sponsorship that ends is deleted. Kept for the client."
    )
    started_at: datetime
    ended_at: datetime | None = Field(description="Always null, for the same reason")
    reflection: str | None
    reflection_status: CommentStatus | None
    reflection_message: str | None = Field(
        description="What happened to the reflection, in Arabic, for its sponsor"
    )
