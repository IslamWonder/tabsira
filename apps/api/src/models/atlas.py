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

«كفالة بصيرة» (decision 60): a published entry nobody has looked after for `ORPHAN_AFTER_DAYS`
turns `orphaned`; its public place is widened to a city, a region or a country, the widening
is recorded in `map_entry_generalisations` (where the earlier cell lives, and nowhere public),
and it is never narrowed again. A member may sponsor an orphaned entry
(`map_entry_sponsorships`), which returns it to `published` at the widened place, with the
author's handle still hidden.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from src.models.base import Base, created_at_column, string_enum
from src.models.public_id import public_id_pk
from src.models.social import COMMENT_MAX, CommentStatus

PLACE_LABEL_MAX = 200
# A sponsor's reflection is as long as a comment, and judged the same way.
SPONSOR_REFLECTION_MAX = COMMENT_MAX


class MapEntryStatus(StrEnum):
    """
    Where an entry is in its life.

    Placed but not shown; shown; hidden by reports until a moderator decides; taken down by a
    moderator (kept for an appeal); withdrawn by its owner (a tombstone with no location); or
    orphaned, which is shown at a widened place without its author's name until someone sponsors it.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    PENDING_REVIEW = "pending_review"
    REMOVED = "removed"
    WITHDRAWN = "withdrawn"
    ORPHANED = "orphaned"


class WidenLevel(StrEnum):
    """How far an orphaned entry's public place was widened; from the finest to the coarsest."""

    GRID = "grid"
    CITY = "city"
    REGION = "region"
    COUNTRY = "country"


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
        # The orphans near a point, and the daily job's scan for entries gone quiet.
        Index(
            "ix_map_entries_orphaned_geom",
            "public_geom",
            postgresql_using="gist",
            postgresql_where=text("status = 'orphaned'"),
        ),
        Index(
            "ix_map_entries_last_active",
            "last_active_at",
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
    # The owner chose to show the insight's photo with the entry (v2 §19); the public copy
    # exists only while the entry is published and the photo rules still allow it.
    with_photo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last sign of life (decision 60): publishing, the author's re-placing, a sponsorship
    # starting, the sponsor's reflection. A view never sets it: nothing is recorded about readers.
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Set once the public place was widened (the daily job); never cleared and never narrowed,
    # and from then on the public answers carry no handle of the author.
    widened_level: Mapped[WidenLevel | None] = mapped_column(
        string_enum(WidenLevel, "widened_level")
    )
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
        BigInteger,
        ForeignKey("map_entries.id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[LocationSource] = mapped_column(string_enum(LocationSource, "source"))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime] = created_at_column()


class MapEntryRetiredId(Base):
    """
    A public id an entry had before its place was widened.

    The id encodes the millisecond the entry was placed, so widening gives the entry a new one
    (`orphan_service`) and the old address answers 410 like a withdrawn entry. The row holds
    the old id and the time, and nothing that leads to the new id.
    """

    __tablename__ = "map_entry_retired_ids"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    retired_at: Mapped[datetime] = created_at_column()


class MapEntryGeneralisation(Base):
    """
    One widening of an entry's public place, and what it was before.

    The earlier public point, cell and label live here and nowhere else; no public or admin
    route reads this table (a test searches every public answer for them). It goes with the
    entry: a withdrawal deletes its rows, since an earlier cell must not outlive the entry.
    """

    __tablename__ = "map_entry_generalisations"
    __table_args__ = (Index("ix_map_entry_generalisations_entry_id", "entry_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("map_entries.id", ondelete="CASCADE", onupdate="CASCADE")
    )
    previous_cell_m: Mapped[int] = mapped_column(Integer)
    previous_public_lat: Mapped[float | None] = mapped_column(Float)
    previous_public_lng: Mapped[float | None] = mapped_column(Float)
    previous_place_label: Mapped[str | None] = mapped_column(String(PLACE_LABEL_MAX))
    new_level: Mapped[WidenLevel] = mapped_column(string_enum(WidenLevel, "new_level"))
    new_label: Mapped[str | None] = mapped_column(String(PLACE_LABEL_MAX))
    reason: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = created_at_column()


class MapEntrySponsorship(Base):
    """
    A member looks after an orphaned entry («كفالة بصيرة»).

    One sponsorship per entry. The sponsor chose to sponsor in public, so their handle is shown
    beside the entry; the reflection is their own words, judged by the same guard as a comment,
    with the comment's states and the same moderation queue, and never scripture. The row exists
    only while the sponsorship does: ending it, withdrawing or removing the entry, or deleting the
    sponsor's account deletes it, reflection included. Its id is public (a report names the
    reflection by it).
    """

    __tablename__ = "map_entry_sponsorships"
    __table_args__ = (
        Index("uq_map_entry_sponsorships_entry_id", "entry_id", unique=True),
        Index("ix_map_entry_sponsorships_user_id", "user_id", text("started_at DESC")),
        # The moderation queue.
        Index(
            "ix_map_entry_sponsorships_pending_review",
            "started_at",
            postgresql_where=text("reflection_status = 'pending_review'"),
        ),
        CheckConstraint(
            "(reflection IS NULL) = (reflection_status IS NULL)", name="reflection_has_state"
        ),
    )

    id: Mapped[int] = public_id_pk("map_entry_sponsorships")
    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("map_entries.id", ondelete="CASCADE", onupdate="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reflection: Mapped[str | None] = mapped_column(String(SPONSOR_REFLECTION_MAX))
    reflection_status: Mapped[CommentStatus | None] = mapped_column(
        string_enum(CommentStatus, "reflection_status")
    )
    reflection_reason: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    started_at: Mapped[datetime] = created_at_column()
    # The names the moderation service and the queue use for a comment's state, reason and time:
    # a reflection is moderated through the same code.
    status: Mapped[CommentStatus | None] = synonym("reflection_status")
    status_reason: Mapped[str | None] = synonym("reflection_reason")
    created_at: Mapped[datetime] = synonym("started_at")
