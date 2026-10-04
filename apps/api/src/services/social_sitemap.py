"""
The sitemap sections of the social network: public posts and public profiles (decision 29).

A search engine is told only what a stranger may read. A post is listed while it is published,
public (never for followers only) and its author's account is active; the moment it is
withdrawn, removed, held or switched to followers only, it leaves the list. A profile is listed
when its member has chosen a handle and has at least one such post, so an empty page is never
advertised. Both are cut into pages by id, oldest first, so a new record lands in the last page
and the pages before it keep their contents and their `lastmod`, which is the record's own
change time.

Importing this module registers both providers; `create_app` imports it.
"""

from __future__ import annotations

from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.social import PostStatus, PostVisibility
from src.services.sitemap_service import Entry, PageStamp, Section, register

# What a stranger may read of a post: the same rule as `feed_service.readable_posts` for a guest.
_PUBLIC_POSTS = (
    f"p.status = '{PostStatus.PUBLISHED.value}' AND p.visibility = '{PostVisibility.PUBLIC.value}' "
    "AND u.is_active AND u.deleted_at IS NULL AND u.handle IS NOT NULL"
)


def post_path(post_id: int) -> str:
    return f"/posts/{post_id}"


def profile_path(handle: str) -> str:
    """Return the member's address with the handle percent-encoded, as the sitemap requires."""
    return f"/u/{quote(handle, safe='')}"


class PostsProvider:
    section = Section.POSTS

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        rows = await db.execute(
            text(
                f"""
                SELECT (numbered.n - 1) / :size AS page, max(numbered.changed) AS lastmod
                FROM (
                    SELECT row_number() OVER (ORDER BY p.id) AS n, p.updated_at AS changed
                    FROM app.posts p JOIN app.users u ON u.id = p.author_id
                    WHERE {_PUBLIC_POSTS}
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
                SELECT p.id, p.updated_at
                FROM app.posts p JOIN app.users u ON u.id = p.author_id
                WHERE {_PUBLIC_POSTS}
                ORDER BY p.id OFFSET :skip LIMIT :size
                """  # noqa: S608 - a constant condition, no input
            ),
            {"skip": page * page_size, "size": page_size},
        )
        # No images yet: a photo's public address belongs to the photo store, and only a
        # published photo of a consenting owner may ever be listed here.
        return [Entry(path=post_path(post_id), lastmod=changed) for post_id, changed in rows]


class ProfilesProvider:
    section = Section.PROFILES

    # Members with a handle and at least one public post, and when either last changed.
    _MEMBERS = f"""
        FROM app.users u
        JOIN (
            SELECT p.author_id, max(p.updated_at) AS last_post
            FROM app.posts p
            WHERE p.status = '{PostStatus.PUBLISHED.value}'
              AND p.visibility = '{PostVisibility.PUBLIC.value}'
            GROUP BY p.author_id
        ) latest ON latest.author_id = u.id
        WHERE u.handle IS NOT NULL AND u.is_active AND u.deleted_at IS NULL
    """  # noqa: S608 - constants only, no input

    async def pages(self, db: AsyncSession, page_size: int) -> list[PageStamp]:
        rows = await db.execute(
            text(
                f"""
                SELECT (numbered.n - 1) / :size AS page, max(numbered.changed) AS lastmod
                FROM (
                    SELECT row_number() OVER (ORDER BY u.id) AS n,
                           GREATEST(u.updated_at, latest.last_post) AS changed
                    {self._MEMBERS}
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
                SELECT u.handle, GREATEST(u.updated_at, latest.last_post) AS changed
                {self._MEMBERS}
                ORDER BY u.id OFFSET :skip LIMIT :size
                """
            ),
            {"skip": page * page_size, "size": page_size},
        )
        return [Entry(path=profile_path(handle), lastmod=changed) for handle, changed in rows]


register(PostsProvider())
register(ProfilesProvider())
