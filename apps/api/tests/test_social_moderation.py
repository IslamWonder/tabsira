"""Moderation decisions: the guard's, a moderator's, and the reports that hold a post back."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from src import clock
from src.errors import AppError, ErrorCode
from src.models import (
    CommentStatus,
    ModerationAction,
    PostStatus,
    RemovalSource,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
)
from src.services import moderation_service
from src.services.moderation_guard import GuardVerdict, Outcome
from tests.support_social import new_comment, new_post

MODERATOR = uuid.uuid4()


async def logged(db_session):
    rows = (await db_session.scalars(select(ModerationAction).order_by(ModerationAction.id))).all()
    return [(r.target_type.value, r.action.value, r.source.value, r.reason) for r in rows]


async def report(db_session, reporter, target, target_type=ReportTarget.POST):
    row = Report(
        reporter_id=reporter.id,
        target_type=target_type,
        target_id=target.id,
        reason=ReportReason.ABUSE,
    )
    db_session.add(row)
    await db_session.flush()
    return row


# ─── The guard's verdict ──────────────────────────────────────────────────────


async def test_a_clear_verdict_publishes_a_post_with_its_time_and_logs_it(make_user, db_session):
    author = await make_user("a@example.com")
    post = await new_post(db_session, author)

    moderation_service.settle(db_session, post, GuardVerdict(Outcome.ALLOW, "clear", {"a": 1}))
    await db_session.flush()

    assert post.status is PostStatus.PUBLISHED
    assert post.published_at is not None
    assert post.status_reason is None
    assert await logged(db_session) == [("post", "published", "guard", "clear")]


async def test_an_uncertain_verdict_holds_a_post_and_a_refusal_rejects_it_with_the_reason(
    make_user, db_session
):
    author = await make_user("a@example.com")
    held = await new_post(db_session, author)
    refused = await new_post(db_session, author)

    moderation_service.settle(db_session, held, GuardVerdict(Outcome.REVIEW, "guard_uncertain"))
    moderation_service.settle(db_session, refused, GuardVerdict(Outcome.REJECT, "hate"))
    await db_session.flush()

    assert (held.status, held.status_reason) == (PostStatus.PENDING_REVIEW, "guard_uncertain")
    assert (refused.status, refused.status_reason) == (PostStatus.REJECTED, "hate")
    assert held.published_at is None
    assert await logged(db_session) == [
        ("post", "held", "guard", "guard_uncertain"),
        ("post", "rejected", "guard", "hate"),
    ]


async def test_the_guard_settles_a_comment_the_same_way_without_a_publication_time(
    make_user, db_session
):
    author = await make_user("a@example.com")
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    one = await new_comment(db_session, post, author, status=CommentStatus.PENDING_REVIEW)
    two = await new_comment(db_session, post, author, status=CommentStatus.PENDING_REVIEW)
    three = await new_comment(db_session, post, author, status=CommentStatus.PENDING_REVIEW)

    moderation_service.settle(db_session, one, GuardVerdict(Outcome.ALLOW, "clear"))
    moderation_service.settle(db_session, two, GuardVerdict(Outcome.REVIEW, "guard_unavailable"))
    moderation_service.settle(db_session, three, GuardVerdict(Outcome.REJECT, "sexual"))

    assert [c.status for c in (one, two, three)] == [
        CommentStatus.PUBLISHED,
        CommentStatus.PENDING_REVIEW,
        CommentStatus.REJECTED,
    ]
    assert [row[0] for row in await logged(db_session)] == ["comment"] * 3


# ─── A moderator's decisions ──────────────────────────────────────────────────


async def test_a_moderator_approves_a_held_post_and_the_reports_on_it_are_dismissed(
    make_user, db_session
):
    author, reader = await make_user("a@example.com"), await make_user("r@example.com")
    post = await new_post(
        db_session, author, status=PostStatus.PENDING_REVIEW, status_reason="reported"
    )
    filed = await report(db_session, reader, post)

    await moderation_service.approve(db_session, post, MODERATOR)
    await db_session.flush()

    assert (post.status, post.status_reason, post.reviewed_by) == (
        PostStatus.PUBLISHED,
        None,
        MODERATOR,
    )
    assert post.published_at is not None
    await db_session.refresh(filed)
    assert filed.status is ReportStatus.DISMISSED
    assert (filed.handled_by, filed.handled_at is not None) == (MODERATOR, True)
    assert await logged(db_session) == [("post", "published", "moderator", None)]


async def test_approving_a_removed_or_refused_post_restores_it_and_keeps_its_first_publication_time(
    make_user, db_session
):
    author = await make_user("a@example.com")
    removed = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    first_time = removed.published_at
    await moderation_service.remove(db_session, removed, MODERATOR, "abuse")
    refused = await new_post(db_session, author, status=PostStatus.REJECTED, status_reason="hate")

    await moderation_service.approve(db_session, removed, MODERATOR)
    await moderation_service.approve(db_session, refused, MODERATOR)
    await db_session.flush()

    assert removed.status is PostStatus.PUBLISHED
    assert (removed.removed_at, removed.removal_source) == (None, None)
    assert removed.published_at == first_time
    assert refused.status is PostStatus.PUBLISHED
    assert [row[1] for row in await logged(db_session)] == ["removed", "restored", "restored"]


async def test_a_moderator_refuses_a_held_post_with_a_reason_and_the_reports_are_actioned(
    make_user, db_session
):
    author, reader = await make_user("a@example.com"), await make_user("r@example.com")
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    filed = await report(db_session, reader, post)

    await moderation_service.reject(db_session, post, MODERATOR, "false_religious_claim")

    assert (post.status, post.status_reason) == (PostStatus.REJECTED, "false_religious_claim")
    assert filed.status is ReportStatus.ACTIONED
    assert await logged(db_session) == [("post", "rejected", "moderator", "false_religious_claim")]


async def test_a_moderator_removes_a_published_post_which_keeps_its_content(make_user, db_session):
    author = await make_user("a@example.com")
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED, reflection="تأمل")

    await moderation_service.remove(db_session, post, MODERATOR, "spam")

    assert post.status is PostStatus.REMOVED
    assert post.removal_source is RemovalSource.MODERATOR
    assert post.removed_at is not None
    assert (post.reflection, post.publication_id is not None) == ("تأمل", True)
    assert await logged(db_session) == [("post", "removed", "moderator", "spam")]


async def test_a_moderator_decides_on_comments_too(make_user, db_session):
    author, reader = await make_user("a@example.com"), await make_user("r@example.com")
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    held = await new_comment(db_session, post, reader, status=CommentStatus.PENDING_REVIEW)
    live = await new_comment(db_session, post, reader)
    other = await new_comment(db_session, post, reader, status=CommentStatus.PENDING_REVIEW)
    filed = await report(db_session, author, live, ReportTarget.COMMENT)

    await moderation_service.approve(db_session, held, MODERATOR)
    await moderation_service.remove(db_session, live, MODERATOR, "abuse")
    await moderation_service.reject(db_session, other, MODERATOR, "spam")

    assert (held.status, live.status, other.status) == (
        CommentStatus.PUBLISHED,
        CommentStatus.REMOVED,
        CommentStatus.REJECTED,
    )
    assert filed.status is ReportStatus.ACTIONED
    assert [row[:2] for row in await logged(db_session)] == [
        ("comment", "published"),
        ("comment", "removed"),
        ("comment", "rejected"),
    ]


async def test_a_decision_closes_only_the_reports_of_its_own_target(make_user, db_session):
    author, reader = await make_user("a@example.com"), await make_user("r@example.com")
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    elsewhere = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    mine = await report(db_session, reader, post)
    theirs = await report(db_session, reader, elsewhere)

    await moderation_service.remove(db_session, post, MODERATOR, "abuse")

    assert (mine.status, theirs.status) == (ReportStatus.ACTIONED, ReportStatus.OPEN)


# ─── Reports that hold a published item back ──────────────────────────────────


async def test_enough_different_reporters_send_a_published_post_back_to_the_queue(
    make_user, db_session
):
    author = await make_user("a@example.com")
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    reporters = [await make_user(f"r{i}@example.com") for i in range(3)]
    for reporter in reporters[:2]:
        await report(db_session, reporter, post)

    below = await moderation_service.hold_if_reported(db_session, post, 3)
    await report(db_session, reporters[2], post)
    reached = await moderation_service.hold_if_reported(db_session, post, 3)

    assert (below, reached) == (False, True)
    assert (post.status, post.status_reason) == (PostStatus.PENDING_REVIEW, "reported")
    assert await logged(db_session) == [("post", "held", "reports", "reported")]
    row = await db_session.scalar(select(ModerationAction))
    assert row.details == {"reporters": 3}


async def test_the_hold_can_be_switched_off_and_never_touches_what_is_not_published(
    make_user, db_session
):
    author, reader = await make_user("a@example.com"), await make_user("r@example.com")
    live = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    draft = await new_post(db_session, author)
    await report(db_session, reader, live)
    await report(db_session, reader, draft)

    assert await moderation_service.hold_if_reported(db_session, live, 0) is False
    assert await moderation_service.hold_if_reported(db_session, draft, 1) is False
    assert (live.status, draft.status) == (PostStatus.PUBLISHED, PostStatus.DRAFT)


async def test_the_reports_of_one_person_count_once_and_closed_ones_not_at_all(
    make_user, db_session
):
    author, reader = await make_user("a@example.com"), await make_user("r@example.com")
    comment_post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    comment = await new_comment(db_session, comment_post, reader)
    filed = await report(db_session, author, comment, ReportTarget.COMMENT)
    filed.status = ReportStatus.DISMISSED
    await db_session.flush()

    assert await moderation_service.hold_if_reported(db_session, comment, 1) is False
    filed.status = ReportStatus.OPEN
    await db_session.flush()
    assert await moderation_service.hold_if_reported(db_session, comment, 1) is True
    assert comment.status is CommentStatus.PENDING_REVIEW


async def test_a_decision_applies_only_to_the_states_it_is_for(make_user, db_session):
    author = await make_user("a@example.com")
    draft = await new_post(db_session, author)
    published = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    held = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    refused = await new_post(db_session, author, status=PostStatus.REJECTED)
    withdrawn = await new_post(
        db_session,
        author,
        status=PostStatus.REMOVED,
        removal_source=RemovalSource.OWNER,
        removed_at=clock.utcnow(),
    )

    attempts = [
        (moderation_service.approve, draft),
        (moderation_service.approve, published),
        (moderation_service.approve, withdrawn),
        (moderation_service.reject, draft),
        (moderation_service.reject, published),
        (moderation_service.reject, refused),
        (moderation_service.reject, withdrawn),
        (moderation_service.remove, draft),
        (moderation_service.remove, held),
        (moderation_service.remove, refused),
        (moderation_service.remove, withdrawn),
    ]
    for decide, item in attempts:
        args = (
            (db_session, item, MODERATOR)
            if decide is moderation_service.approve
            else (
                db_session,
                item,
                MODERATOR,
                "abuse",
            )
        )
        with pytest.raises(AppError) as caught:
            await decide(*args)
        assert (caught.value.code, caught.value.status_code) == (ErrorCode.CONFLICT, 409)

    # What an author withdrew stays withdrawn, and nothing was logged for the refusals.
    assert withdrawn.status is PostStatus.REMOVED
    assert await logged(db_session) == []


async def test_a_decision_reads_the_item_fresh_so_a_withdrawal_in_between_wins(
    make_user, db_session
):
    author = await make_user("a@example.com")
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    # The moderator's screen showed the post held; the author withdrew it since.
    await db_session.execute(
        text(
            "UPDATE app.posts SET status = 'removed', removal_source = 'owner', "
            "publication_id = NULL WHERE id = :id"
        ),
        {"id": post.id},
    )

    with pytest.raises(AppError):
        await moderation_service.approve(db_session, post, MODERATOR)

    assert post.status is PostStatus.REMOVED
    assert post.publication_id is None


def test_a_reason_is_known_only_when_the_app_defines_it():
    assert moderation_service.known_reason("hate") == "hate"
    assert moderation_service.known_reason("guard_uncertain") == "guard_uncertain"
    assert moderation_service.known_reason("a moderator's own words") is None
    assert moderation_service.known_reason(None) is None
