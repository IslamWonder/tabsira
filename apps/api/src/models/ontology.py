"""
The world ontology (`app.ontology_entities`) and the terms it did not know (`app.ontology_candidates`).

The ontology is imported from `data/world-ontology.xlsx` and is never edited by the
application. What the application learns goes into the candidates table, where a
person reviews it and merges the accepted terms into a new version of the file.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class CandidateKind(StrEnum):
    """What a model proposed that the ontology does not hold."""

    LABEL = "label"  # a thing, as a detector or a vision model named it
    CONCEPT = "concept"  # a meaning a planner proposed for a scene


class CandidateStatus(StrEnum):
    """Where a candidate is in its review."""

    NEW = "new"
    ACCEPTED = "accepted"  # merged into a new version of the ontology file
    REJECTED = "rejected"


def _one_of(column: str, enum: type[StrEnum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


class OntologyEntity(Base):
    """
    One entity of the world ontology: a thing, an action or a situation and what it relates to.

    The Arabic text is stored as the workbook has it, and `raw` keeps the cells of
    the row untouched. `label_norm`, `related_norm` and `search_text` are the search
    forms (see `src.arabic`); the trigram index serves similar-text search, the
    others serve exact lookups. A catch-all entity («نبات غير محدد», «موقف غير واضح»)
    is what a label resolves to when nothing more specific is known.
    """

    __tablename__ = "ontology_entities"
    __table_args__ = (
        CheckConstraint("id ~ '^E[0-9]{3,}$'", name="id_format"),
        Index("ix_ontology_entities_label_norm", "label_norm"),
        Index("ix_ontology_entities_related_norm", "related_norm", postgresql_using="gin"),
        Index(
            "ix_ontology_entities_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index("ix_ontology_entities_domain", "domain"),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    label_ar: Mapped[str] = mapped_column(Text)
    related_objects: Mapped[list[str]] = mapped_column(ARRAY(Text))
    actions_and_uses: Mapped[list[str]] = mapped_column(ARRAY(Text))
    contextual_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text))
    special_constraint: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text)
    is_catch_all: Mapped[bool] = mapped_column(Boolean, server_default=false())
    # The cells of the row exactly as the workbook holds them, and the row number.
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    label_norm: Mapped[str] = mapped_column(Text)
    related_norm: Mapped[list[str]] = mapped_column(ARRAY(Text))
    search_text: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OntologyCandidate(Base):
    """
    A label or a concept a model proposed that the ontology could not resolve.

    One row per distinct term and kind: each new sighting adds to `count` and, up
    to a small limit, to `examples`. A reviewer accepts or rejects the term; an
    accepted one is merged into the next version of the workbook, never into the
    existing one, and `entity_id` can name the entity it was folded into.
    """

    __tablename__ = "ontology_candidates"
    __table_args__ = (
        UniqueConstraint("kind", "term_norm", name="uq_ontology_candidates_kind_term_norm"),
        CheckConstraint(_one_of("kind", CandidateKind), name="kind"),
        CheckConstraint(_one_of("status", CandidateStatus), name="status"),
        CheckConstraint("count >= 1", name="count_positive"),
        Index("ix_ontology_candidates_status_count", "status", "count"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    term: Mapped[str] = mapped_column(Text)
    term_norm: Mapped[str] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    # Which stages proposed it: detector, vision model, planner.
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    examples: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'new'"))
    entity_id: Mapped[str | None] = mapped_column(
        String(16), ForeignKey("ontology_entities.id", ondelete="SET NULL")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
