"""
«أطلس بصائر العالم»: a saved insight placed on the real map, at an approximate location.

Two tables keep the two locations apart in storage, as the extension's section 10 asks:

- `map_entries` is the public side. It holds the published point, which is the centre
  of the grid cell the capture point fell in (`src/geo/privacy.py`, computed on the
  server with `GEO_APPROX_CELL_METERS` when the entry is placed), the cell size, the
  nearest populated place from GeoNames as a label, and the state.
- `map_capture_points` is the private side: the exact point its owner gave, with its
  source, its accuracy and when it was measured. It is read only by its owner's routes
  and by the account export; no public query joins it, and withdrawing the entry
  deletes it.

An entry belongs to an account (never a guest), is made from one insight, and takes a
public id (decision 37). Withdrawing leaves a tombstone so the entry's address answers
410, with the public point cleared.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum
from src.models.public_id import public_id_pk

PLACE_LABEL_MAX = 200


class MapEntryStatus(StrEnum):
    """
    Where an entry is in its life.

    Placed but not shown; shown; hidden by reports until a moderator decides; taken down by a
    moderator (kept for an appeal); or withdrawn by its owner (a tombstone with no location).
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    PENDING_REVIEW = "pending_review"
    REMOVED = "removed"
    WITHDRAWN = "withdrawn"


class LocationSource(StrEnum):
    """Where the capture point came from (extension §3); none of them proves presence."""

    DEVICE_CAPTURE = "device_capture"
    PHOTO_EXIF = "photo_exif"
    USER_SELECTED = "user_selected"


class LocationMeaning(StrEnum):
    """What the point stands for: where the photo was taken, or a public place the owner named."""

    CAPTURE_POINT = "capture_point"
    PUBLIC_PLACE = "public_place"


class MapEntry(Base):
    """The public side of a placed insight: the approximate point, its label and its state."""

    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __tablename__ = "map_entries"
    __table_args__ = (
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="published_has_time"
        ),
        CheckConstraint(
            "status <> 'published' OR (public_lat IS NOT NULL AND public_lng IS NOT NULL)",
            name="published_has_point",
        ),
        # The atlas: what is published, inside a map window, newest first.
        Index(
            "ix_map_entries_public_geom",
            "public_geom",
            postgresql_using="gist",
            postgresql_where=text("status = 'published'"),
        ),
        Index(
            "ix_map_entries_published",
            text("published_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'published'"),
        ),
        Index(
            "ix_map_entries_place",
            "place_geoname_id",
            postgresql_where=text("status = 'published'"),
        ),
        Index("ix_map_entries_user_id", "user_id"),
        # One live entry per insight; a withdrawn tombstone stays beside the next one, so an
        # address shared before a withdrawal never comes back to life.
        Index(
            "uq_map_entries_live_insight",
            "insight_id",
            unique=True,
            postgresql_where=text("status <> 'withdrawn'"),
        ),
        # The moderation queue.
        Index(
            "ix_map_entries_pending_review",
            "created_at",
            postgresql_where=text("status = 'pending_review'"),
        ),
    )

    id: Mapped[int] = public_id_pk("map_entries")
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    insight_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("insights.id", ondelete="CASCADE")
    )
    # The published point: the centre of the grid cell, never the capture point itself.
    public_lat: Mapped[float | None] = mapped_column(Float)
    public_lng: Mapped[float | None] = mapped_column(Float)
    public_geom: Mapped[Any | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    cell_m: Mapped[int] = mapped_column(Integer)
    location_meaning: Mapped[LocationMeaning] = mapped_column(
        string_enum(LocationMeaning, "location_meaning")
    )
    # The nearest populated place (GeoNames) the public point is labelled with, when one is in range.
    place_geoname_id: Mapped[int | None] = mapped_column(BigInteger)
    place_label: Mapped[str | None] = mapped_column(String(PLACE_LABEL_MAX))
    admin_label: Mapped[str | None] = mapped_column(String(PLACE_LABEL_MAX))
    country_iso2: Mapped[str | None] = mapped_column(String(2))
    country_label: Mapped[str | None] = mapped_column(String(PLACE_LABEL_MAX))
    status: Mapped[MapEntryStatus] = mapped_column(
        string_enum(MapEntryStatus, "status"),
        default=MapEntryStatus.DRAFT,
        server_default=MapEntryStatus.DRAFT.value,
    )
    # A code the owner is shown with the outcome (see src/messages.py), never a moderator's words.
    status_reason: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The moderator's account. No foreign key: the decision outlives their account.
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MapCapturePoint(Base):
    """The private side: the exact point the owner gave, read by the owner's routes alone."""

    __tablename__ = "map_capture_points"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("accuracy_m IS NULL OR accuracy_m >= 0", name="accuracy_positive"),
    )

    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("map_entries.id", ondelete="CASCADE"), primary_key=True
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[LocationSource] = mapped_column(string_enum(LocationSource, "source"))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime] = created_at_column()
