"""
Posts: made from a verified insight, submitted through the guard, read by those who may.

A post starts as a draft the author alone can see, made from a copy of one of their own
verified insights; submitting it runs the guard, which publishes it, refuses it with a reason
or holds it for a moderator. The author reads the outcome on their own copy. Withdrawing a
post erases its content and makes its address answer 410 Gone. Every route checks the
session, the owner, the post's state, its audience and the blocks: an id grants nothing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select

from src.deps import (
    CurrentUser,
    DbDep,
    InsightSourceDep,
    IpHashDep,
    OptionalUser,
    PhotoStoreDep,
    PublicMember,
    SettingsDep,
    TextGuardDep,
    limited,
    require_social,
)
from src.models.social import InsightPublication, Post
from src.models.user import User
from src.scans.deps import RedisDep
from src.schemas.social import MyPostsPage, PostCreateIn, PostIdPath, PostOut, PostPatch
from src.services import auth_service, post_service, post_view, publication_service, view_service
from src.services import cursor as cursors
from src.services.post_service import PostRow
from src.services.social_limits import WriteKind
from src.services.window_limiter import WindowLimiter, too_many_requests
from src.storage.photos import PhotoStore

router = APIRouter(tags=["posts"], dependencies=[Depends(require_social)])

PAGE_DEFAULT = 20
# Views per hour and per worker, from one address (an IPv6 /64) and from one site (an IPv6 /48):
# far above anyone reading, low enough that inflating a count from a block of addresses takes a
# while. No budget over all addresses: a flood could then stop every view from counting.
VIEWS_PER_ADDRESS = 300
VIEWS_PER_SITE = 3000
VIEW_WINDOW_SECONDS = 3600


class ViewLimits:
    """The budgets of the view beacon, per address and per site; no overall one."""

    def __init__(
        self,
        per_address: int = VIEWS_PER_ADDRESS,
        per_site: int = VIEWS_PER_SITE,
        window_seconds: float = VIEW_WINDOW_SECONDS,
    ) -> None:
        self.per_address = WindowLimiter(per_address, window_seconds)
        self.per_site = WindowLimiter(per_site, window_seconds)

    def hit(self, address_hash: str, site_hash: str) -> float | None:
        """Count one view; None when allowed, else the seconds to wait."""
        retry_after = self.per_address.hit(address_hash)
        if retry_after is None:
            retry_after = self.per_site.hit(site_hash)
        return retry_after


PAGE_MAX = 50
Limit = Annotated[int, Query(ge=1, le=PAGE_MAX)]


async def _one(db: DbDep, row: PostRow, viewer: User | None, photos: PhotoStore) -> PostOut:
    return (await post_view.build_posts(db, [row], viewer, photos=photos))[0]


@router.post(
    "/posts",
    status_code=status.HTTP_201_CREATED,
    summary="Start a draft from a verified insight",
    dependencies=[limited(WriteKind.POST)],
)
async def create_post(
    body: PostCreateIn,
    user: PublicMember,
    db: DbDep,
    source: InsightSourceDep,
    settings: SettingsDep,
    photos: PhotoStoreDep,
) -> PostOut:
    """
    Copy one of the caller's verified insights into a publication and open a draft on it.

    The copy is what is previewed and what is published; it is never edited afterwards. The
    caller's own words go in `reflection`, apart from the insight. 409 `INSIGHT_NOT_PUBLISHABLE`
    says why an insight cannot be published; 409 `PUBLIC_IDENTITY_REQUIRED` that the caller
    has no handle yet. Nothing is visible to anyone else until the draft is submitted.
    """
    publication = await publication_service.create_publication(
        db, source, user, body.insight_id, settings, publish_photo=body.photo
    )
    post = post_service.create_draft(db, user, publication, body.reflection, body.visibility)
    await db.flush()
    await db.commit()
    return await _one(db, PostRow(post, publication, user), user, photos)


@router.get("/posts/{post_id}", summary="One post")
async def get_post(
    post_id: PostIdPath, viewer: OptionalUser, db: DbDep, photos: PhotoStoreDep
) -> PostOut:
    """
    Return a post the caller may read.

    404 for one that does not exist or that the caller may not see (a draft, a post held or
    refused, one for followers the caller does not follow, one behind a block); 410 Gone for
    one that was withdrawn or removed.
    """
    row = await post_service.get_readable(db, post_id, viewer)
    return await _one(db, row, viewer, photos)


def _view_limits(request: Request) -> ViewLimits:
    limits: ViewLimits | None = getattr(request.app.state, "view_limits", None)
    if limits is None:
        limits = ViewLimits()
        request.app.state.view_limits = limits
    return limits


def limit_views(request: Request, settings: SettingsDep, ip_hash: IpHashDep) -> None:
    """Answer 429 past the address's budget, before the session or the post is looked up."""
    site = auth_service.hash_ip(settings, request.client.host if request.client else None, 48)
    retry_after = _view_limits(request).hit(ip_hash, site)
    if retry_after is not None:
        raise too_many_requests(retry_after, "Too many views. Try again later.")


@router.post(
    "/posts/{post_id}/view",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Count one view of an open post",
    dependencies=[Depends(limit_views)],
)
async def view_post(
    post_id: PostIdPath,
    viewer: OptionalUser,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    ip_hash: IpHashDep,
    request: Request,
) -> Response:
    """
    Count one view: once per viewer a day, never the author's, never a bot's.

    Sent by the post page once it has opened, so the web server's render, a link preview or a
    crawler fetching the post is not a view. Answers as `GET /posts/{post_id}` does for a post
    the caller may not read, and counts nothing then; 429 past the budget of the address or of
    its site, before the session or the post is looked up. Who viewed is never stored (see
    `view_service`).
    """
    row = await post_service.get_readable(db, post_id, viewer)
    await view_service.record(
        db,
        redis,
        settings.hash_key,
        row.post,
        viewer,
        ip_hash=ip_hash,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/posts/{post_id}",
    summary="Edit a draft",
    dependencies=[limited(WriteKind.POST)],
)
async def patch_post(
    post_id: PostIdPath, body: PostPatch, user: PublicMember, db: DbDep, photos: PhotoStoreDep
) -> PostOut:
    """Change a draft's reflection or audience; a refused post becomes a draft again."""
    row = await post_service.get_owned(db, post_id, user)
    post_service.update_draft(
        row.post,
        reflection=body.reflection,
        visibility=body.visibility,
        reflection_given="reflection" in body.model_fields_set,
    )
    await db.commit()
    return await _one(db, row, user, photos)


@router.post(
    "/posts/{post_id}/submit",
    summary="Submit a draft for publication",
    dependencies=[limited(WriteKind.POST)],
)
async def submit_post(
    post_id: PostIdPath, user: PublicMember, db: DbDep, guard: TextGuardDep, photos: PhotoStoreDep
) -> PostOut:
    """
    Run a draft through the guard.

    The answer says what happened: `published`, `rejected` with its reason, or
    `pending_review` while a moderator looks. A failed guard holds the post, never
    publishes it. 409 for a post that is not a draft.
    """
    row = await post_service.get_owned(db, post_id, user)
    post = await post_service.submit(db, row, guard, photos=photos)
    await db.commit()
    return await _one(db, PostRow(post, row.publication, user), user, photos)


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw a post",
    dependencies=[limited(WriteKind.POST)],
)
async def delete_post(
    post_id: PostIdPath, user: CurrentUser, db: DbDep, photos: PhotoStoreDep
) -> Response:
    """
    Withdraw a post, a draft or a published one.

    Its reflection, its comments, its likes and its saves are erased at once, with the public
    copy of its photo, it leaves every feed and every profile, and its address answers 410 Gone
    from then on (this route too).
    """
    row = await post_service.get_owned(db, post_id, user)
    await post_service.withdraw(db, row, photos=photos)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/posts", summary="The caller's own posts, in every state")
async def my_posts(
    user: CurrentUser,
    db: DbDep,
    photos: PhotoStoreDep,
    cursor: str | None = None,
    limit: Limit = PAGE_DEFAULT,
) -> MyPostsPage:
    """
    List the caller's posts, newest first, with what happened to each.

    Withdrawn posts are gone and are not listed; one a moderator removed is, with its reason.
    """
    position = cursors.decode(cursor)
    statement = (
        select(Post, InsightPublication)
        .join(InsightPublication, InsightPublication.id == Post.publication_id)
        .where(Post.author_id == user.id)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    if position is not None:
        statement = statement.where(
            (Post.created_at < position.at)
            | ((Post.created_at == position.at) & (Post.id < position.id))
        )
    rows = (await db.execute(statement)).all()
    page = rows[:limit]
    items = await post_view.build_posts(
        db, [PostRow(post, publication, user) for post, publication in page], user, photos=photos
    )
    last = page[-1][0] if len(rows) > limit else None
    return MyPostsPage(
        items=items,
        next_cursor=(
            None if last is None else cursors.encode(cursors.Cursor(at=last.created_at, id=last.id))
        ),
    )
