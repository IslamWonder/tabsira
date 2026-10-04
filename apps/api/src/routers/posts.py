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

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select

from src.deps import (
    CurrentUser,
    DbDep,
    InsightSourceDep,
    OptionalUser,
    PublicMember,
    TextGuardDep,
    limited,
    require_social,
)
from src.models.social import InsightPublication, Post
from src.models.user import User
from src.schemas.social import MyPostsPage, PostCreateIn, PostIdPath, PostOut, PostPatch
from src.services import cursor as cursors
from src.services import post_service, post_view, publication_service
from src.services.post_service import PostRow
from src.services.social_limits import WriteKind

router = APIRouter(tags=["posts"], dependencies=[Depends(require_social)])

PAGE_DEFAULT = 20
PAGE_MAX = 50
Limit = Annotated[int, Query(ge=1, le=PAGE_MAX)]


async def _one(db: DbDep, row: PostRow, viewer: User | None) -> PostOut:
    return (await post_view.build_posts(db, [row], viewer))[0]


@router.post(
    "/posts",
    status_code=status.HTTP_201_CREATED,
    summary="Start a draft from a verified insight",
    dependencies=[limited(WriteKind.POST)],
)
async def create_post(
    body: PostCreateIn, user: PublicMember, db: DbDep, source: InsightSourceDep
) -> PostOut:
    """
    Copy one of the caller's verified insights into a publication and open a draft on it.

    The copy is what is previewed and what is published; it is never edited afterwards. The
    caller's own words go in `reflection`, apart from the insight. 409 `INSIGHT_NOT_PUBLISHABLE`
    says why an insight cannot be published; 409 `PUBLIC_IDENTITY_REQUIRED` that the caller
    has no handle yet. Nothing is visible to anyone else until the draft is submitted.
    """
    publication = await publication_service.create_publication(db, source, user, body.insight_id)
    post = post_service.create_draft(db, user, publication, body.reflection, body.visibility)
    await db.flush()
    await db.commit()
    return await _one(db, PostRow(post, publication, user), user)


@router.get("/posts/{post_id}", summary="One post")
async def get_post(post_id: PostIdPath, viewer: OptionalUser, db: DbDep) -> PostOut:
    """
    Return a post the caller may read.

    404 for one that does not exist or that the caller may not see (a draft, a post held or
    refused, one for followers the caller does not follow, one behind a block); 410 Gone for
    one that was withdrawn or removed.
    """
    row = await post_service.get_readable(db, post_id, viewer)
    return await _one(db, row, viewer)


@router.patch(
    "/posts/{post_id}",
    summary="Edit a draft",
    dependencies=[limited(WriteKind.POST)],
)
async def patch_post(
    post_id: PostIdPath, body: PostPatch, user: PublicMember, db: DbDep
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
    return await _one(db, row, user)


@router.post(
    "/posts/{post_id}/submit",
    summary="Submit a draft for publication",
    dependencies=[limited(WriteKind.POST)],
)
async def submit_post(
    post_id: PostIdPath, user: PublicMember, db: DbDep, guard: TextGuardDep
) -> PostOut:
    """
    Run a draft through the guard.

    The answer says what happened: `published`, `rejected` with its reason, or
    `pending_review` while a moderator looks. A failed guard holds the post, never
    publishes it. 409 for a post that is not a draft.
    """
    row = await post_service.get_owned(db, post_id, user)
    post = await post_service.submit(db, row, guard)
    await db.commit()
    return await _one(db, PostRow(post, row.publication, user), user)


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw a post",
    dependencies=[limited(WriteKind.POST)],
)
async def delete_post(post_id: PostIdPath, user: CurrentUser, db: DbDep) -> Response:
    """
    Withdraw a post, a draft or a published one.

    Its reflection, its comments, its likes and its saves are erased at once, it leaves every
    feed and every profile, and its address answers 410 Gone from then on (this route too).
    """
    row = await post_service.get_owned(db, post_id, user)
    await post_service.withdraw(db, row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/posts", summary="The caller's own posts, in every state")
async def my_posts(
    user: CurrentUser,
    db: DbDep,
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
        db, [PostRow(post, publication, user) for post, publication in page], user
    )
    last = page[-1][0] if len(rows) > limit else None
    return MyPostsPage(
        items=items,
        next_cursor=(
            None if last is None else cursors.encode(cursors.Cursor(at=last.created_at, id=last.id))
        ),
    )
