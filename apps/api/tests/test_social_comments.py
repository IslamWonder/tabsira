"""Comments and replies: the guard, the thread, blocks, deletion."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from src.features import FeatureFlag
from src.models import Comment, CommentStatus, ModerationAction
from src.services import comment_service
from src.services.social_limits import SocialLimits, WriteKind
from tests.helpers import any_id, switched
from tests.support_social import ALLOW, REJECT, REVIEW, draft_post, publish_post


@pytest.fixture
def account_settings(account_settings):
    """These tests write and read comments, which are off until the owners enable them."""
    return switched(account_settings, on=[FeatureFlag.SOCIAL_COMMENTS])


async def comment(member, post_id, body="تعليق", **extra):
    return await member.http.post(f"/posts/{post_id}/comments", json={"body": body, **extra})


async def listing(member, post_id, **params):
    return (await member.http.get(f"/posts/{post_id}/comments", params=params)).json()


# ─── Writing ──────────────────────────────────────────────────────────────────


async def test_a_clear_comment_is_published_and_the_guard_saw_only_its_words(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    guard.texts.clear()

    response = await comment(reader, post_id, "  تأمل جميل  ")

    body = response.json()
    assert response.status_code == 201
    assert (body["body"], body["status"], body["is_mine"], body["replies"]) == (
        "تأمل جميل",
        "published",
        True,
        [],
    )
    assert body["author"] == {"handle": "reader", "public_name": "reader name"}
    assert body["status_message"] is None
    assert guard.texts == ["تأمل جميل"]
    assert (
        await db_session.scalar(select(ModerationAction).order_by(ModerationAction.id.desc()))
    ).action.value == "published"
    assert (await author.http.get(f"/posts/{post_id}")).json()["comment_count"] == 1


async def test_an_uncertain_comment_waits_and_only_its_author_sees_it(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    post_id = await publish_post(author, make_insight)
    guard.verdict = REVIEW

    body = (await comment(reader, post_id)).json()

    assert body["status"] == "pending_review"
    assert body["status_message"] == "يحتاج إلى مراجعة مشرف قبل نشره."
    assert [c["id"] for c in (await listing(reader, post_id))["items"]] == [body["id"]]
    assert (await listing(author, post_id))["items"] == []
    assert (await listing(guest, post_id))["items"] == []
    assert (await author.http.get(f"/posts/{post_id}")).json()["comment_count"] == 0


async def test_a_refused_comment_tells_its_author_why_and_is_shown_to_nobody_else(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    guard.verdict = REJECT

    body = (await comment(reader, post_id)).json()

    assert body["status"] == "rejected"
    assert body["status_message"] == "لم يُقبل لأنه يخالف قواعد المجتمع: إساءة أو مضايقة."
    assert (await listing(author, post_id))["items"] == []


async def test_a_comment_needs_a_verified_account_with_a_public_identity_and_a_published_post(
    make_member, make_insight, guard
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    unverified = await make_member("fresh", verified=False)
    nameless = await make_member("nameless", identity=False)
    stranger = await make_member("stranger")
    post_id = await publish_post(author, make_insight)
    private_id = await publish_post(author, make_insight, visibility="followers")
    draft_id = (await draft_post(author, make_insight(author))).json()["id"]

    assert (await comment(guest, post_id)).status_code == 401
    assert (await comment(unverified, post_id)).json()["error"] == "EMAIL_NOT_VERIFIED"
    assert (await comment(nameless, post_id)).json()["error"] == "PUBLIC_IDENTITY_REQUIRED"
    assert (await comment(stranger, private_id)).status_code == 404
    assert (await comment(stranger, any_id())).status_code == 404
    draft = await comment(author, draft_id)
    assert (draft.status_code, draft.json()["error"]) == (409, "CONFLICT")


async def test_a_comment_has_words_and_not_too_many(make_member, make_insight, guard):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    empty = await comment(author, post_id, "   ")
    long = await comment(author, post_id, "x" * 501)
    control = await comment(author, post_id, "a\u0007b")
    bidi = await comment(author, post_id, "a \u202eb")
    extra = await author.http.post(
        f"/posts/{post_id}/comments", json={"body": "x", "status": "published"}
    )

    assert [r.status_code for r in (empty, long, control, bidi, extra)] == [422] * 5


async def test_comments_are_rate_limited_per_account(make_member, make_insight, guard, account_app):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)
    account_app.state.social_limits = SocialLimits({WriteKind.COMMENT: (1, 100, 60)})

    first = await comment(author, post_id)
    second = await comment(author, post_id)

    assert (first.status_code, second.status_code) == (201, 429)


# ─── Replies ──────────────────────────────────────────────────────────────────


async def test_a_reply_is_nested_under_its_comment_and_a_reply_cannot_be_answered(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    top = (await comment(reader, post_id, "أولى")).json()
    reply = await comment(author, post_id, "رد", parent_id=top["id"])
    deeper = await comment(reader, post_id, "رد على الرد", parent_id=reply.json()["id"])

    thread = (await listing(reader, post_id))["items"]

    assert reply.status_code == 201
    assert (deeper.status_code, deeper.json()["error"]) == (409, "CONFLICT")
    assert [c["body"] for c in thread] == ["أولى"]
    assert [r["body"] for r in thread[0]["replies"]] == ["رد"]
    assert thread[0]["replies"][0]["replies"] == []
    assert thread[0]["replies"][0]["author"]["handle"] == "author"
    assert (await author.http.get(f"/posts/{post_id}")).json()["comment_count"] == 2


async def test_a_reply_must_answer_a_comment_of_the_same_post_that_the_author_may_read(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    other_id = await publish_post(author, make_insight)
    elsewhere = (await comment(reader, other_id)).json()
    guard.verdict = REVIEW
    held = (await comment(reader, post_id)).json()
    guard.verdict = ALLOW

    assert (await comment(author, post_id, parent_id=elsewhere["id"])).status_code == 404
    assert (await comment(author, post_id, parent_id=held["id"])).status_code == 404
    assert (await comment(author, post_id, parent_id=any_id())).status_code == 404


async def test_a_comment_takes_a_limited_number_of_replies(
    make_member, make_insight, guard, monkeypatch
):
    monkeypatch.setattr(comment_service, "MAX_REPLIES", 2)
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)
    top = (await comment(author, post_id)).json()

    codes = [(await comment(author, post_id, parent_id=top["id"])).status_code for _ in range(3)]

    assert codes == [201, 201, 409]


# ─── Reading ──────────────────────────────────────────────────────────────────


async def test_the_thread_is_oldest_first_in_pages_and_public(make_member, make_insight, guard):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    post_id = await publish_post(author, make_insight)
    ids = [(await comment(author, post_id, f"تعليق {i}")).json()["id"] for i in range(3)]

    first = await listing(guest, post_id, limit=2)
    second = await listing(guest, post_id, limit=2, cursor=first["next_cursor"])

    assert [c["id"] for c in first["items"]] == ids[:2]
    assert [c["id"] for c in second["items"]] == ids[2:]
    assert second["next_cursor"] is None
    assert all(c["is_mine"] is False and c["status_message"] is None for c in first["items"])


async def test_the_thread_of_a_post_the_caller_may_not_read_is_a_404_and_a_gone_one_a_410(
    make_member, make_insight, guard
):
    author = await make_member("author")
    stranger = await make_member("stranger")
    private_id = await publish_post(author, make_insight, visibility="followers")
    gone_id = await publish_post(author, make_insight)
    await author.http.delete(f"/posts/{gone_id}")

    assert (await stranger.http.get(f"/posts/{private_id}/comments")).status_code == 404
    assert (await stranger.http.get(f"/posts/{gone_id}/comments")).status_code == 410
    bad = await stranger.http.get(f"/posts/{private_id}/comments", params={"cursor": "x"})
    # The post is checked before the cursor is read.
    assert bad.status_code == 404


async def test_a_forged_cursor_is_refused(make_member, make_insight, guard):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    response = await author.http.get(f"/posts/{post_id}/comments", params={"cursor": "forged"})

    assert (response.status_code, response.json()["error"]) == (400, "INVALID_CURSOR")


# ─── Blocks ───────────────────────────────────────────────────────────────────


async def test_a_block_removes_the_other_persons_comments_from_the_thread_and_restores_them(
    make_member, make_insight, guard
):
    author = await make_member("author")
    ann = await make_member("ann")
    bob = await make_member("bob")
    post_id = await publish_post(author, make_insight)
    top = (await comment(bob, post_id, "من بوب")).json()
    await comment(author, post_id, "رد المؤلف", parent_id=top["id"])
    await comment(ann, post_id, "من آن")

    await ann.http.put("/blocks/bob")
    seen_by_ann = [c["body"] for c in (await listing(ann, post_id))["items"]]
    seen_by_bob = [c["body"] for c in (await listing(bob, post_id))["items"]]
    seen_by_author = [c["body"] for c in (await listing(author, post_id))["items"]]
    await ann.http.delete("/blocks/bob")
    restored = [c["body"] for c in (await listing(ann, post_id))["items"]]

    assert seen_by_ann == ["من آن"]
    assert seen_by_bob == ["من بوب"]
    assert seen_by_author == ["من بوب", "من آن"]
    assert restored == ["من بوب", "من آن"]


async def test_a_comment_by_someone_the_posts_author_blocked_is_gone_for_everyone(
    make_member, make_insight, guard
):
    author = await make_member("author")
    bob = await make_member("bob")
    carol = await make_member("carol")
    post_id = await publish_post(author, make_insight)
    await comment(bob, post_id, "من بوب")
    await comment(carol, post_id, "من كارول")

    await author.http.put("/blocks/bob")

    assert [c["body"] for c in (await listing(carol, post_id))["items"]] == ["من كارول"]


async def test_nobody_replies_to_a_comment_they_cannot_read(make_member, make_insight, guard):
    author = await make_member("author")
    ann = await make_member("ann")
    bob = await make_member("bob")
    post_id = await publish_post(author, make_insight)
    top = (await comment(bob, post_id)).json()
    await ann.http.put("/blocks/bob")

    assert (await comment(ann, post_id, parent_id=top["id"])).status_code == 404


async def test_a_comment_of_a_disabled_account_is_not_listed(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    bob = await make_member("bob")
    post_id = await publish_post(author, make_insight)
    await comment(bob, post_id)
    bob.user.is_active = False
    await db_session.flush()

    assert (await listing(author, post_id))["items"] == []


# ─── Deleting ─────────────────────────────────────────────────────────────────


async def test_an_author_deletes_their_own_comment_and_its_replies_go_with_it(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    top = (await comment(reader, post_id)).json()
    await comment(author, post_id, parent_id=top["id"])

    response = await reader.http.delete(f"/posts/{post_id}/comments/{top['id']}")

    assert response.status_code == 204
    assert await db_session.scalar(select(func.count()).select_from(Comment)) == 0
    assert (await listing(author, post_id))["items"] == []
    assert (await author.http.get(f"/posts/{post_id}")).json()["comment_count"] == 0


async def test_only_the_author_of_a_comment_deletes_it(make_member, make_insight, guard):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    top = (await comment(reader, post_id)).json()
    guest = await make_member(signed_in=False)

    assert (await author.http.delete(f"/posts/{post_id}/comments/{top['id']}")).status_code == 404
    assert (await guest.http.delete(f"/posts/{post_id}/comments/{top['id']}")).status_code == 401
    assert (await reader.http.delete(f"/posts/{post_id}/comments/{any_id()}")).status_code == 404
    other_post = await publish_post(author, make_insight)
    assert (
        await reader.http.delete(f"/posts/{other_post}/comments/{top['id']}")
    ).status_code == 404
    assert len((await listing(author, post_id))["items"]) == 1


async def test_a_held_comment_can_be_deleted_by_its_author(make_member, make_insight, guard):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    guard.verdict = REVIEW
    held = (await comment(reader, post_id)).json()

    assert (await reader.http.delete(f"/posts/{post_id}/comments/{held['id']}")).status_code == 204
    assert (await listing(reader, post_id))["items"] == []


async def test_a_comment_on_a_withdrawn_post_is_already_erased_with_it(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    top = (await comment(reader, post_id)).json()
    await author.http.delete(f"/posts/{post_id}")

    assert (await reader.http.delete(f"/posts/{post_id}/comments/{top['id']}")).status_code == 404


async def test_a_person_takes_their_words_back_after_they_can_no_longer_read_the_post(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    fan = await make_member("fan")
    blocker = await make_member("blocker")
    post_id = await publish_post(author, make_insight, visibility="followers")
    await fan.http.put("/u/author/follow")
    await blocker.http.put("/u/author/follow")
    mine = (await comment(fan, post_id, "تعليقي")).json()
    theirs = (await comment(blocker, post_id, "تعليق آخر")).json()
    await fan.http.delete("/u/author/follow")
    await blocker.http.put("/blocks/author")

    assert (await fan.http.get(f"/posts/{post_id}")).status_code == 404
    assert (await fan.http.delete(f"/posts/{post_id}/comments/{mine['id']}")).status_code == 204
    assert (
        await blocker.http.delete(f"/posts/{post_id}/comments/{theirs['id']}")
    ).status_code == 204
    assert await db_session.scalar(select(func.count()).select_from(Comment)) == 0


async def test_replies_that_are_held_or_refused_do_not_use_up_a_comments_room(
    make_member, make_insight, guard, monkeypatch
):
    monkeypatch.setattr(comment_service, "MAX_REPLIES", 1)
    author = await make_member("author")
    spammer = await make_member("spammer")
    post_id = await publish_post(author, make_insight)
    top = (await comment(author, post_id)).json()
    guard.verdict = REJECT
    refused = await comment(spammer, post_id, parent_id=top["id"])
    guard.verdict = REVIEW
    held = await comment(spammer, post_id, parent_id=top["id"])
    guard.verdict = ALLOW

    real = await comment(author, post_id, parent_id=top["id"])
    over = await comment(author, post_id, parent_id=top["id"])

    assert [r.status_code for r in (refused, held, real, over)] == [201, 201, 201, 409]


async def test_a_comment_deleted_while_the_guard_judged_it_ends_in_a_404(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)

    async def delete_meanwhile():
        await db_session.execute(text("DELETE FROM app.comments"))

    guard.during = delete_meanwhile

    response = await comment(author, post_id)

    assert response.status_code == 404


async def test_the_statuses_of_a_comment_are_the_four_of_the_decision():
    assert {s.value for s in CommentStatus} == {
        "pending_review",
        "published",
        "rejected",
        "removed",
    }
