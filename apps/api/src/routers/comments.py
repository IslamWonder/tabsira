"""
Comments on a post, and replies to them.

Reading needs only the right to read the post. Writing needs a verified address and a public
identity, and a published post the caller may read. A new comment goes through the guard before
anyone but its author sees it. A comment can be deleted by its author; knowing an id grants
nothing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status

from src.deps import (
    CurrentUser,
    DbDep,
    OptionalUser,
    PublicMember,
    TextGuardDep,
    limited,
    require_social,
)
from src.models.social import Comment
from src.models.user import User
from src.schemas.social import (
    CommentCreateIn,
    CommentIdPath,
    CommentOut,
    CommentPage,
    MemberOut,
    PostIdPath,
)
from src.services import comment_service, post_service
from src.services import cursor as cursors
from src.services.comment_service import Thread
from src.services.post_view import outcome_message
from src.services.social_limits import WriteKind

router = APIRouter(tags=["comments"], dependencies=[Depends(require_social)])

PAGE_DEFAULT = 20
PAGE_MAX = 50


def _out(
    comment: Comment, author: User, viewer_id: uuid.UUID | None, replies: list[CommentOut]
) -> CommentOut:
    mine = viewer_id is not None and comment.author_id == viewer_id
    return CommentOut(
        id=comment.id,
        author=MemberOut(handle=author.handle or "", public_name=author.public_name or ""),
        body=comment.body,
        created_at=comment.created_at,
        status=comment.status,
        status_message=outcome_message(comment.status, comment.status_reason) if mine else None,
        is_mine=mine,
        replies=replies,
    )


def _thread_out(thread: Thread, viewer_id: uuid.UUID | None) -> CommentOut:
    replies = [_out(reply, author, viewer_id, []) for reply, author in thread.replies]
    return _out(thread.comment, thread.author, viewer_id, replies)


@router.get("/posts/{post_id}/comments", summary="A post's comments")
async def list_comments(
    post_id: PostIdPath,
    viewer: OptionalUser,
    db: DbDep,
    cursor: str | None = None,
    limit: int = Query(PAGE_DEFAULT, ge=1, le=PAGE_MAX),
) -> CommentPage:
    """
    List a post's comments oldest first, each with its replies.

    Only published comments, and the caller's own in any state. A comment by someone the caller
    blocked, or who blocked the caller, or whom the post's author blocked, is not listed.
    """
    await post_service.get_readable(db, post_id, viewer)
    threads, next_cursor = await comment_service.list_threads(
        db, post_id, viewer, cursors.decode(cursor), limit
    )
    viewer_id = viewer.id if viewer is not None else None
    return CommentPage(
        items=[_thread_out(thread, viewer_id) for thread in threads], next_cursor=next_cursor
    )


@router.post(
    "/posts/{post_id}/comments",
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a post, or reply to a comment",
    dependencies=[limited(WriteKind.COMMENT)],
)
async def create_comment(
    post_id: PostIdPath,
    body: CommentCreateIn,
    user: PublicMember,
    db: DbDep,
    guard: TextGuardDep,
) -> CommentOut:
    """
    Add a comment, or a reply (`parent_id`) to a comment that is not itself a reply.

    The answer says what the guard decided: `published`, `rejected` with its reason, or
    `pending_review` while a moderator looks; until it is published only its author sees it.
    """
    row = await post_service.get_interactable(db, post_id, user)
    comment = await comment_service.create_comment(db, row.post, user, body.body, body.parent_id)
    settled = await comment_service.judge(db, comment, guard)
    await db.commit()
    return _out(settled, user, user.id, [])


@router.delete(
    "/posts/{post_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the caller's own comment",
    dependencies=[limited(WriteKind.COMMENT)],
)
async def delete_comment(
    post_id: PostIdPath, comment_id: CommentIdPath, user: CurrentUser, db: DbDep
) -> Response:
    """Delete one's own comment, whatever its state; its replies go with it. Someone else's is a 404."""
    await post_service.get_readable(db, post_id, user)
    comment, _ = await comment_service.get_visible(db, post_id, comment_id, user)
    if comment.author_id != user.id:
        raise comment_service.not_found()
    await comment_service.delete_comment(db, comment)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
