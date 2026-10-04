"""Declarative base of the application tables (schema `app`) and the columns they share."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit constraint and index names, so a migration and the models always
# agree on them and a constraint can be dropped by a name that is predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

APP_SCHEMA = "app"
# The scripture reference data, the world ontology and the learning path: tables of
# the same metadata and the same Alembic chain, kept apart so they can be exported
# and installed as one verified archive (docs/CORPUS.md, decision 57).
CORPUS_SCHEMA = "corpus"


class Base(DeclarativeBase):
    """Base class of every table that lives in the `app` schema."""

    metadata = MetaData(schema=APP_SCHEMA, naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """
    Return a UUID primary key that PostgreSQL 18 generates, time-ordered (version 7).

    Time order keeps new rows at the end of the index; the id is known after the
    insert, which the ORM reads back in the same round trip.
    """
    return mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))


def created_at_column() -> Mapped[datetime]:
    """Return a creation-time column, set by the database unless the caller gives one."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def string_enum(enum: type[StrEnum], name: str) -> Enum:
    """
    Return a column type that stores a `StrEnum` as text, guarded by a CHECK constraint.

    Not a PostgreSQL enum type: adding a value later is a plain constraint
    change in a migration, and the stored text is readable anywhere. The
    constraint is named `ck_<table>_<name>` by the naming convention.
    """
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )
