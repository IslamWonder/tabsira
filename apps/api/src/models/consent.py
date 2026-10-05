"""Consent records: an append-only history of what the user agreed to and withdrew."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DDL, Boolean, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum, uuid_pk


class ConsentKind(StrEnum):
    TERMS = "terms"  # the terms of use
    PRIVACY = "privacy"  # the privacy policy
    PHOTO_STORAGE = "photo_storage"  # keep my photos on the server
    PERSONALIZATION = "personalization"  # tailor the explanations to my choices
    MEMORY = "memory"  # remember my earlier insights
    PUBLIC_FULL_NAME = "public_full_name"  # show my real full name beside my handle (decision 63)


class Consent(Base):
    """
    One answer to one consent question, at one time, for one version of its text.

    Rows are only ever inserted: the database refuses to update one (a trigger,
    below), and a row leaves only together with its user. The current answer is
    the latest row of a kind; withdrawing is a new row with `granted` false.
    """

    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_user_id_kind_created_at", "user_id", "kind", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[ConsentKind] = mapped_column(string_enum(ConsentKind, "kind"))
    version: Mapped[str] = mapped_column(String(32))
    granted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = created_at_column()


# The same two statements are written out in the migration that creates the
# table; this copy builds the trigger when a test schema is created from the models.
APPEND_ONLY_STATEMENTS = (
    """
    CREATE OR REPLACE FUNCTION app.consents_forbid_update() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'consents are append-only' USING ERRCODE = 'integrity_constraint_violation';
    END
    $$
    """,
    """
    CREATE TRIGGER consents_forbid_update BEFORE UPDATE ON app.consents
    FOR EACH ROW EXECUTE FUNCTION app.consents_forbid_update()
    """,
)

for _statement in APPEND_ONLY_STATEMENTS:
    # SQLAlchemy ships DDL without type hints.
    _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
    event.listen(Consent.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))
