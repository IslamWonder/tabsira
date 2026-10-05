"""Reports of posts and comments, with their reasons."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.features import FeatureFlag
from src.models import Post, PostStatus, Report, ReportReason, ReportTarget
from src.services.social_limits import SocialLimits, WriteKind
from tests.helpers import any_id, switched
from tests.support_social import publish_post


@pytest.fixture
def account_settings(account_settings):
    """These tests write and read comments, which are off until the owners enable them."""
    return switched(account_settings, on=[FeatureFlag.SOCIAL_COMMENTS])


async def report(member, target_type, target_id, reason="abuse", **extra):
    return await member.http.post(
        "/reports",
        json={"target_type": target_type, "target_id": str(target_id), "reason": reason, **extra},
    )


async def test_every_reason_of_the_decision_is_accepted_including_the_two_for_places():
    assert {reason.value for reason in ReportReason} >= {
        "abuse",
        "spam",
        "false_religious_claim",
        "unauthorised_photo",
        "wrong_place",
        "private_information",
    }


async def test_a_post_is_reported_with_a_reason_and_details(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    response = await report(
        reader, "post", post_id, "private_information", details="  يكشف موقع بيت  "
    )

    assert response.status_code == 201
    stored = await db_session.scalar(select(Report))
    assert response.json() == {"id": str(stored.id)}
    assert (stored.reporter_id, stored.target_type, stored.target_id) == (
        reader.user.id,
        ReportTarget.POST,
        int(post_id),
    )
    assert (stored.reason, stored.details, stored.status.value) == (
        ReportReason.PRIVATE_INFORMATION,
        "يكشف موقع بيت",
        "open",
    )


async def test_reporting_the_same_thing_twice_answers_with_the_first_report(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    first = await report(reader, "post", post_id, "spam")
    second = await report(reader, "post", post_id, "abuse")

    assert first.json() == second.json()
    assert await db_session.scalar(select(func.count()).select_from(Report)) == 1
    assert (await db_session.scalar(select(Report))).reason is ReportReason.SPAM


async def test_a_comment_is_reported(make_member, make_insight, guard, db_session):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    comment_id = (await reader.http.post(f"/posts/{post_id}/comments", json={"body": "x"})).json()[
        "id"
    ]

    response = await report(author, "comment", comment_id, "false_religious_claim")

    assert response.status_code == 201
    stored = await db_session.scalar(select(Report))
    assert (stored.target_type, stored.target_id) == (ReportTarget.COMMENT, int(comment_id))


async def test_nobody_reports_their_own_words(make_member, make_insight, guard):
    author = await make_member("author")
    post_id = await publish_post(author, make_insight)
    comment_id = (await author.http.post(f"/posts/{post_id}/comments", json={"body": "x"})).json()[
        "id"
    ]

    assert (await report(author, "post", post_id)).json()["error"] == "BAD_REQUEST"
    assert (await report(author, "comment", comment_id)).json()["error"] == "BAD_REQUEST"


async def test_only_what_the_reporter_may_read_can_be_reported(make_member, make_insight, guard):
    author = await make_member("author")
    stranger = await make_member("stranger")
    commenter = await make_member("commenter")
    private_id = await publish_post(author, make_insight, visibility="followers")
    post_id = await publish_post(author, make_insight)
    comment_id = (
        await commenter.http.post(f"/posts/{post_id}/comments", json={"body": "x"})
    ).json()["id"]
    await stranger.http.put("/blocks/commenter")

    assert (await report(stranger, "post", private_id)).status_code == 404
    assert (await report(stranger, "post", any_id())).status_code == 404
    assert (await report(stranger, "comment", any_id())).status_code == 404
    # A block hides the commenter's comment, so it cannot be reported by the blocker.
    assert (await report(stranger, "comment", comment_id)).status_code == 404


async def test_a_comment_on_a_post_that_is_gone_cannot_be_reported(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    other = await make_member("other")
    post_id = await publish_post(author, make_insight)
    comment_id = (await reader.http.post(f"/posts/{post_id}/comments", json={"body": "x"})).json()[
        "id"
    ]
    await author.http.put("/blocks/other")

    # The post is behind a block for `other`: the comment answers as if it did not exist.
    assert (await report(other, "comment", comment_id)).status_code == 404


async def test_a_report_needs_a_verified_session_and_a_known_reason(
    make_member, make_insight, guard
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    unverified = await make_member("fresh", verified=False)
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    assert (await report(guest, "post", post_id)).status_code == 401
    assert (await report(unverified, "post", post_id)).status_code == 403
    assert (await report(reader, "post", post_id, "no-such-reason")).status_code == 422
    assert (await report(reader, "page", post_id)).status_code == 422
    assert (await report(reader, "post", "abc")).status_code == 422
    long = await report(reader, "post", post_id, details="x" * 1001)
    assert long.status_code == 422


async def test_enough_different_reporters_hold_a_published_post_until_a_moderator_decides(
    make_member, make_insight, guard, account_app, account_settings, db_session
):
    account_app.state.settings = account_settings.model_copy(
        update={"social_report_hold_threshold": 2}
    )
    author = await make_member("author")
    one = await make_member("one")
    two = await make_member("two")
    guest = await make_member(signed_in=False)
    post_id = await publish_post(author, make_insight)

    await report(one, "post", post_id)
    still_up = (await guest.http.get(f"/posts/{post_id}")).status_code
    await report(one, "post", post_id, "spam")
    await report(two, "post", post_id)

    assert still_up == 200
    assert (await guest.http.get(f"/posts/{post_id}")).status_code == 404
    mine = (await author.http.get(f"/posts/{post_id}")).json()
    assert (mine["status"], mine["status_reason"]) == ("pending_review", "reported")
    assert mine["status_message"] == "وصلتنا عنه بلاغات، فأُخفي مؤقتًا حتى يراجعه مشرف."
    assert (await db_session.scalar(select(Post))).status is PostStatus.PENDING_REVIEW


async def test_a_post_is_not_held_by_reports_when_the_threshold_is_zero(
    make_member, make_insight, guard, account_app, account_settings
):
    account_app.state.settings = account_settings.model_copy(
        update={"social_report_hold_threshold": 0}
    )
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    post_id = await publish_post(author, make_insight)
    for index in range(4):
        reader = await make_member(f"reader{index}")
        await report(reader, "post", post_id)

    assert (await guest.http.get(f"/posts/{post_id}")).status_code == 200


async def test_reports_are_rate_limited_per_account(make_member, make_insight, guard, account_app):
    account_app.state.social_limits = SocialLimits({WriteKind.REPORT: (1, 100, 60)})
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    first = await report(reader, "post", post_id)
    second = await report(reader, "post", post_id)

    assert (first.status_code, second.status_code) == (201, 429)
