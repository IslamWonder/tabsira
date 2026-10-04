"""
The insights section of the sitemap: the insights their owners made public (decision 29).

An insight is listed while it is published and its owner's account is live; the
moment it is withdrawn it leaves the list. Pages are cut by id, oldest first, and
`lastmod` is the moment of publication, the record's own change. No images: no
photo of an insight is published yet. Importing this module registers the
provider; `create_app` imports it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.insight_view import public_path
from src.services.sitemap_service import Entry, PageStamp, Section, register

# What a stranger may read: the same rule as `insight_publishing.published`, an account that
# declared an age under 13 excluded (v2 §5).
_PUBLIC = (
    "i.published_at IS NOT NULL AND i.engine <> 'demo' AND u.is_active AND u.deleted_at IS NULL "
    "AND NOT EXISTS (SELECT 1 FROM app.profiles pr "
    "WHERE pr.user_id = u.id AND pr.age_range = 'under_13')"
)


class InsightsProvider:
    section = Section.INSIGHTS

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        rows = await db.execute(
            text(
                f"""
                SELECT (numbered.n - 1) / :size AS page, max(numbered.changed) AS lastmod
                FROM (
                    SELECT row_number() OVER (ORDER BY i.id) AS n, i.published_at AS changed
                    FROM app.insights i JOIN app.users u ON u.id = i.user_id
                    WHERE {_PUBLIC}
                ) AS numbered
                GROUP BY 1 ORDER BY 1
                """  # noqa: S608 - a constant condition, no input
            ),
            {"size": page_size},
        )
        return [PageStamp(page=page, lastmod=lastmod) for page, lastmod in rows]

    async def entries(self, db: AsyncSession, page: int, page_size: int) -> list[Entry]:
        rows = await db.execute(
            text(
                f"""
                SELECT i.id, i.published_at
                FROM app.insights i JOIN app.users u ON u.id = i.user_id
                WHERE {_PUBLIC}
                ORDER BY i.id OFFSET :skip LIMIT :size
                """  # noqa: S608 - a constant condition, no input
            ),
            {"skip": page * page_size, "size": page_size},
        )
        return [
            Entry(path=public_path(insight_id), lastmod=changed) for insight_id, changed in rows
        ]


register(InsightsProvider())
