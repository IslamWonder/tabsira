"""Import every model here so Alembic and `create_all` see all of them."""

from __future__ import annotations

from src.models.base import Base
from src.models.geo_base import GeoBase
from src.models.geonames import (
    GeoAlternateName,
    GeoCountryInfo,
    GeoHierarchy,
    GeoName,
    GeoPostalCode,
)

__all__ = [
    "Base",
    "GeoAlternateName",
    "GeoBase",
    "GeoCountryInfo",
    "GeoHierarchy",
    "GeoName",
    "GeoPostalCode",
]
