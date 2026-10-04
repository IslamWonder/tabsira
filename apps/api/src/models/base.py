"""Declarative base of the application tables (schema `app`)."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

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


class Base(DeclarativeBase):
    """Base class of every table that lives in the `app` schema."""

    metadata = MetaData(schema=APP_SCHEMA, naming_convention=NAMING_CONVENTION)
