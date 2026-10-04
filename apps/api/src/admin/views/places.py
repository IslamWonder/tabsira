"""GeoNames in the admin area: read-only and searchable."""

from __future__ import annotations

import re
from typing import Any

from sqladmin.filters import BooleanFilter
from sqlalchemy import Select
from starlette.requests import Request

from src.admin.base import ReadOnlyView, labelled
from src.admin.dashboard import estimated_geonames
from src.models.geonames import GeoName

CATEGORY = "Places"
CATEGORY_ICON = "fa-solid fa-earth-africa"
_ARABIC = re.compile("[\u0600-\u06ff]")


class GeoNameAdmin(ReadOnlyView, model=GeoName):
    """
    The places GeoNames gave us. They are imported by the geodata chain and never edited.

    The table holds millions of rows, so the page avoids what makes a view of it slow: a
    search in Latin letters uses the name's trigram index, and the total shown without a
    search or a filter is the planner's estimate, not an exact count. A search in Arabic
    letters reads the Arabic name, which has no index, and takes a few seconds.
    """

    name = "GeoName"
    name_plural = "GeoNames"
    icon = "fa-solid fa-location-dot"
    category = CATEGORY
    category_icon = CATEGORY_ICON

    column_list = [
        GeoName.geoname_id,
        GeoName.name,
        GeoName.ar_name,
        GeoName.country_code,
        GeoName.admin1_code,
        GeoName.feature_class,
        GeoName.feature_code,
        GeoName.population,
        GeoName.is_active,
    ]
    column_details_list = [
        *column_list,
        GeoName.admin2_code,
        GeoName.timezone,
        GeoName.latitude,
        GeoName.longitude,
        GeoName.modification_date,
    ]
    column_labels = labelled(column_details_list)
    column_searchable_list = [GeoName.name, GeoName.ar_name]
    column_sortable_list = [GeoName.name, GeoName.population, GeoName.country_code]
    column_default_sort = [(GeoName.population, True)]
    column_filters = [BooleanFilter(GeoName.is_active, "Active")]
    page_size = 50

    def search_query(self, stmt: Select[Any], term: str) -> Select[Any]:
        """Match the Arabic name when the term has Arabic letters, else the indexed name."""
        column = GeoName.ar_name if _ARABIC.search(term) else GeoName.name
        return stmt.where(column.icontains(term, autoescape=True))

    async def count(self, request: Request, stmt: Select[Any] | None = None) -> int:
        """Count exactly when the list is narrowed, and use the estimate for the whole table."""
        asked = request.query_params
        narrowed = "search" in asked or any(
            filter_.parameter_name in asked for filter_ in self.get_filters()
        )
        if stmt is None or narrowed:
            return await super().count(request, stmt)
        estimate = await self._estimate()
        return estimate if estimate > 0 else await super().count(request, stmt)

    async def _estimate(self) -> int:
        async with self.session_maker() as db:
            return await estimated_geonames(db)
