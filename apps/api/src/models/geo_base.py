"""Declarative base of the immutable reference tables (schema `geodata`)."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from src.models.base import NAMING_CONVENTION

GEODATA_SCHEMA = "geodata"


class GeoBase(DeclarativeBase):
    """Base class of every table that lives in the `geodata` schema."""

    metadata = MetaData(schema=GEODATA_SCHEMA, naming_convention=NAMING_CONVENTION)
