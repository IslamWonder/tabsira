"""
The `places` section of the sitemap (decision 29): the public place pages of the atlas.

A place is listed while at least one published entry of an active member with a handle is
labelled with it, so an empty page is never advertised; its `lastmod` is the day (in UTC) of the
newest of those entries, never the hour, as the public pages themselves give a day only. Pages
are cut by GeoNames id, ascending. Importing this module registers the
provider; `create_app` imports it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.atlas import MapEntryStatus
from src.services.sitemap_service import Entry, PageStamp, Section, register


def place_path(geoname_id: int) -> str:
    return f"/atlas/places/{geoname_id}"


class PlacesProvider:
    section = Section.PLACES

    _PLACES = f"""
        FROM (
            SELECT e.place_geoname_id AS geoname_id,
                   date_trunc('day', max(e.published_at), 'UTC') AS changed
            FROM app.map_entries e JOIN app.users u ON u.id = e.user_id
            WHERE e.status = '{MapEntryStatus.PUBLISHED.value}'
              AND e.place_geoname_id IS NOT NULL
              AND u.is_active AND u.deleted_at IS NULL AND u.handle IS NOT NULL
            GROUP BY e.place_geoname_id
        ) places
    """  # noqa: S608 - constants only, no input

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        rows = await db.execute(
            text(
                f"""
                SELECT (numbered.n - 1) / :size AS page, max(numbered.changed) AS lastmod
                FROM (
                    SELECT row_number() OVER (ORDER BY places.geoname_id) AS n, places.changed
                    {self._PLACES}
                ) AS numbered
                GROUP BY 1 ORDER BY 1
                """  # noqa: S608 - constants only, no input
            ),
            {"size": page_size},
        )
        return [PageStamp(page=page, lastmod=lastmod) for page, lastmod in rows]

    async def entries(self, db: AsyncSession, page: int, page_size: int) -> list[Entry]:
        rows = await db.execute(
            text(
                f"""
                SELECT places.geoname_id, places.changed
                {self._PLACES}
                ORDER BY places.geoname_id OFFSET :skip LIMIT :size
                """
            ),
            {"skip": page * page_size, "size": page_size},
        )
        return [Entry(path=place_path(geoname_id), lastmod=changed) for geoname_id, changed in rows]


register(PlacesProvider())
