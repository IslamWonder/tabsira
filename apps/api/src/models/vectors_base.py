"""Declarative base of the derived, rebuildable vectors (schema `vectors`, decision 48)."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from src.models.base import NAMING_CONVENTION

VECTORS_SCHEMA = "vectors"


class VectorsBase(DeclarativeBase):
    """
    Base class of every table that lives in the `vectors` schema.

    Its own metadata, so its own Alembic chain (`alembic_vectors`) owns it, run
    after the app chain because its keys point at `app` tables. A key to an
    `app` table names the column object, not a string: a string resolves only
    inside one metadata.
    """

    metadata = MetaData(schema=VECTORS_SCHEMA, naming_convention=NAMING_CONVENTION)
