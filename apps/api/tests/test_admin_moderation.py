"""
The moderation queue: held and reported posts and comments, decided one at a time.

Every decision goes through the moderation service (the moderation log and the reports
follow), the reason is a code the app defines and never the moderator's words, a decision
made on a stale screen is refused, and the audit log keeps the item's id and the decision's
name, never the text.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.models import (
    AuditAction,
    Comment,
    CommentStatus,
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    Post,
    PostStatus,
    RemovalSource,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
)
from tests.support_admin import audit_rows, csrf_of
from tests.support_social import new_comment, new_post

QUEUE = "/admin/moderation-queue"


def page_of(kind: str, item_id: int) -> str:
    return f"{QUEUE}/{kind}/{item_id}"


async def report(db, reporter, kind: str, item_id: int, **columns) -> Report:
    columns.setdefault("reason", ReportReason.SPAM)
    row = Report(
        reporter_id=reporter.id, target_type=ReportTarget(kind), target_id=item_id, **columns
    )
    db.add(row)
    await db.flush()
    return row


async def decide(http, kind, item_id, decision, reason=None):
    data = {"csrf_token": await csrf_of(http)}
    if reason is not None:
        data["reason"] = reason
    return await http.post(f"{page_of(kind, item_id)}/{decision}", data=data)


async def log_rows(db, kind: str, item_id: int) -> list[ModerationAction]:
    return list(
        (
            await db.scalars(
                select(ModerationAction)
                .where(ModerationAction.target_type == kind, ModerationAction.target_id == item_id)
                .order_by(ModerationAction.id)
            )
        ).all()
    )


@pytest.fixture
async def authors(make_user):
    return await make_user("author@example.com"), await make_user("reader@example.com")


# ─── The queue ─────────────────────────────────────────────────────


async def test_the_queue_lists_held_items_and_reported_published_ones_oldest_first(
    admin, db_session, authors
):
    http, me = admin
    author, reader = authors
    held = await new_post(
        db_session, author, status=PostStatus.PENDING_REVIEW, status_reason="guard_uncertain"
    )
    reported = await new_post(db_session, author, status=PostStatus.PUBLISHED, reflection="ر")
    quiet = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    draft = await new_post(db_session, author)
    await report(db_session, reader, "post", reported.id)
    await report(db_session, reader, "post", quiet.id, status=ReportStatus.DISMISSED)
    held_comment = await new_comment(
        db_session, quiet, author, status=CommentStatus.PENDING_REVIEW, body="ت"
    )
    fine_comment = await new_comment(db_session, quiet, author)

    page = await http.get(QUEUE)

    assert page.status_code == 200
    body = page.text
    assert "2 posts" in body
    assert "1 comment" in body
    assert body.index(f"post {held.id}") < body.index(f"post {reported.id}")
    assert f"post {quiet.id}" not in body
    assert f"post {draft.id}" not in body
    assert f"comment {held_comment.id}" in body
    assert f"comment {fine_comment.id}" not in body
    assert "guard_uncertain" in body
    assert "ر" not in body.split("<tbody>")[1]
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.LIST][-1]
    assert (row.model, row.admin_user_id) == ("moderation-queue", me.id)


async def test_an_empty_queue_says_so(admin):
    http, _ = admin

    page = await http.get(QUEUE)

    assert "No post is waiting." in page.text
    assert "No comment is waiting." in page.text


# ─── An item's page ────────────────────────────────────────────────


async def test_a_posts_page_shows_its_text_its_insight_its_reports_its_log_and_the_fitting_decisions(
    admin, db_session, authors
):
    http, me = admin
    author, reader = authors
    post = await new_post(
        db_session,
        author,
        status=PostStatus.PENDING_REVIEW,
        status_reason="guard_uncertain",
        reflection="كلام الكاتب",
    )
    await report(db_session, reader, "post", post.id, details="تفاصيل المبلّغ")
    db_session.add(
        ModerationAction(
            target_type="post",
            target_id=post.id,
            action=ModerationActionKind.HELD,
            source=ModerationSource.GUARD,
            reason="guard_uncertain",
        )
    )
    await db_session.flush()

    page = await http.get(page_of("post", post.id))

    assert page.status_code == 200
    body = page.text
    assert 'id="item-text" dir="rtl" lang="ar">كلام الكاتب</p>' in body
    assert "Published insight" in body
    assert "تفاصيل المبلّغ" in body
    assert "pending_review (guard_uncertain)" in body
    assert "held" in body and "guard" in body
    assert 'id="approve"' in body
    assert 'id="reject"' in body
    assert 'id="remove"' not in body
    assert 'name="reason"' in body
    assert "spam · " in body
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.VIEW][-1]
    assert (row.model, row.record_id, row.admin_user_id) == (
        "moderation-queue",
        f"post:{post.id}",
        me.id,
    )


async def test_a_published_item_offers_removal_and_a_removed_one_only_approval(
    admin, db_session, authors
):
    http, _ = admin
    author, _ = authors
    published = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    comment = await new_comment(db_session, published, author, status=CommentStatus.REMOVED)

    post_page = await http.get(page_of("post", published.id))
    comment_page = await http.get(page_of("comment", comment.id))

    assert 'id="remove"' in post_page.text
    assert 'id="approve"' not in post_page.text
    assert 'id="reject"' not in post_page.text
    assert 'id="approve"' in comment_page.text
    assert "Publish it again." in comment_page.text
    assert 'id="remove"' not in comment_page.text
    assert "No text of the author" not in comment_page.text


async def test_a_draft_and_a_withdrawn_post_take_no_decision(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    draft = await new_post(db_session, author)

    page = await http.get(page_of("post", draft.id))

    assert "Nothing applies to this item as it is now." in page.text
    for button in ("approve", "reject", "remove"):
        assert f'id="{button}"' not in page.text


async def test_an_unknown_item_or_kind_has_no_page(admin, db_session):
    http, _ = admin

    assert (await http.get(page_of("post", 999_999))).status_code == 404
    assert (await http.get(page_of("photo", 1))).status_code == 404
    assert (await decide(http, "post", 999_999, "approve")).status_code == 404
    assert (await decide(http, "photo", 1, "approve")).status_code == 404


# ─── Decisions ─────────────────────────────────────────────────────


async def test_approving_a_held_post_publishes_it_closes_its_reports_and_logs_it(
    admin, db_session, authors, moving_clock
):
    http, me = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    filed = await report(db_session, reader, "post", post.id)

    response = await decide(http, "post", post.id, "approve")

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"{QUEUE}?decided=post%3A{post.id}")
    await db_session.refresh(post)
    assert (post.status, post.reviewed_by, post.published_at) == (
        PostStatus.PUBLISHED,
        me.id,
        moving_clock.now,
    )
    await db_session.refresh(filed)
    assert (filed.status, filed.handled_by) == (ReportStatus.DISMISSED, me.id)
    rows = await log_rows(db_session, "post", post.id)
    assert [(r.action, r.source, r.actor_id) for r in rows] == [
        (ModerationActionKind.PUBLISHED, ModerationSource.MODERATOR, me.id)
    ]
    audit = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE][-1]
    assert (audit.model, audit.record_id, audit.admin_user_id) == (
        "moderation-queue",
        f"post:{post.id}",
        me.id,
    )
    assert audit.details == {"reason": "approve"}
    queue = await http.get(response.headers["location"])
    assert f"Decided: post:{post.id}." in queue.text
    assert f"post {post.id}" not in queue.text.split("<tbody>")[-1]


async def test_rejecting_a_held_comment_records_the_reason_code_the_author_is_shown(
    admin, db_session, authors
):
    http, me = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    comment = await new_comment(db_session, post, author, status=CommentStatus.PENDING_REVIEW)
    filed = await report(db_session, reader, "comment", comment.id)

    response = await decide(http, "comment", comment.id, "reject", reason="spam")

    assert response.status_code == 303
    await db_session.refresh(comment)
    assert (comment.status, comment.status_reason, comment.reviewed_by) == (
        CommentStatus.REJECTED,
        "spam",
        me.id,
    )
    await db_session.refresh(filed)
    assert filed.status is ReportStatus.ACTIONED
    rows = await log_rows(db_session, "comment", comment.id)
    assert [(r.action, r.reason) for r in rows] == [(ModerationActionKind.REJECTED, "spam")]
    audit = [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE][-1]
    assert (audit.record_id, audit.details) == (f"comment:{comment.id}", {"reason": "reject"})


async def test_removing_a_reported_post_takes_it_down_as_a_moderator(
    admin, db_session, authors, moving_clock
):
    http, me = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    await report(db_session, reader, "post", post.id, reason=ReportReason.ABUSE)

    response = await decide(http, "post", post.id, "remove", reason="harassment")

    assert response.status_code == 303
    await db_session.refresh(post)
    assert (post.status, post.status_reason, post.removal_source, post.removed_at) == (
        PostStatus.REMOVED,
        "harassment",
        RemovalSource.MODERATOR,
        moving_clock.now,
    )
    rows = await log_rows(db_session, "post", post.id)
    assert [(r.action, r.reason, r.actor_id) for r in rows] == [
        (ModerationActionKind.REMOVED, "harassment", me.id)
    ]


async def test_a_moderators_own_words_are_never_a_reason(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)

    for reason in (None, "", "you are rude", "SPAM"):
        response = await decide(http, "post", post.id, "reject", reason=reason)
        assert response.status_code == 400, reason
        assert "Choose a reason from the list" in response.text

    await db_session.refresh(post)
    assert post.status is PostStatus.PENDING_REVIEW
    assert await log_rows(db_session, "post", post.id) == []
    assert not [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE]


async def test_a_decision_that_no_longer_fits_the_item_is_refused_and_the_page_reloaded(
    admin, db_session, authors
):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)
    withdrawn = await new_post(
        db_session,
        author,
        status=PostStatus.REMOVED,
        removal_source=RemovalSource.OWNER,
    )

    stale = await decide(http, "post", post.id, "remove", reason="spam")
    revived = await decide(http, "post", withdrawn.id, "approve")

    assert stale.status_code == 409
    assert "it was reloaded" in stale.text
    assert "pending_review" in stale.text
    assert revived.status_code == 409
    await db_session.refresh(post)
    await db_session.refresh(withdrawn)
    assert post.status is PostStatus.PENDING_REVIEW
    assert withdrawn.status is PostStatus.REMOVED
    assert await log_rows(db_session, "post", post.id) == []
    assert not [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE]


async def test_an_unknown_decision_is_not_a_page(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)

    assert (await decide(http, "post", post.id, "feature")).status_code == 404
    await db_session.refresh(post)
    assert post.status is PostStatus.PENDING_REVIEW


async def test_a_decision_is_a_post_with_the_token(admin, db_session, authors):
    http, _ = admin
    author, _ = authors
    post = await new_post(db_session, author, status=PostStatus.PENDING_REVIEW)

    assert (await http.get(f"{page_of('post', post.id)}/approve")).status_code == 405
    assert (await http.post(f"{page_of('post', post.id)}/approve")).status_code == 403
    await db_session.refresh(post)
    assert post.status is PostStatus.PENDING_REVIEW


# ─── The reports and the moderation log ────────────────────────────


async def test_reports_and_the_moderation_log_are_listed_but_never_changed(
    admin, db_session, authors
):
    http, _ = admin
    author, reader = authors
    post = await new_post(db_session, author, status=PostStatus.PUBLISHED)
    filed = await report(db_session, reader, "post", post.id, details="تفاصيل")
    await decide(http, "post", post.id, "remove", reason="spam")
    token = await csrf_of(http)

    reports = await http.get("/admin/report/list")
    one = await http.get(f"/admin/report/details/{filed.id}")
    log = await http.get("/admin/moderation-action/list")

    assert reports.status_code == 200
    assert str(post.id) in reports.text
    assert "تفاصيل" not in reports.text
    assert "تفاصيل" in one.text
    assert log.status_code == 200
    assert "removed" in log.text and "moderator" in log.text
    for path in ("report/create", f"report/edit/{filed.id}", "moderation-action/create"):
        assert (await http.get(f"/admin/{path}")).status_code == 403
    assert (
        await http.delete(f"/admin/report/delete?pks={filed.id}", headers={"X-CSRF-Token": token})
    ).status_code == 403
    assert (await http.get("/admin/report/export/csv")).status_code == 403
    assert (await db_session.scalars(select(Report))).all() == [filed]
    assert len((await db_session.scalars(select(Post))).all()) == 1
    assert (await db_session.scalars(select(Comment))).all() == []


@pytest.mark.parametrize(
    "path", [QUEUE, f"{QUEUE}/post/1", "/admin/report/list", "/admin/moderation-action/list"]
)
async def test_a_signed_out_browser_reaches_nothing(anon, path):
    assert (await anon.get(path)).status_code == 302
