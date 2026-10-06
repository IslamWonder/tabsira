# ruff: noqa: F811
"""One post per published insight (decision 68): `PUT /insights/{id}/post` and `ensure_post`."""

from __future__ import annotations

from sqlalchemy import func, select

from src.models import InsightPublication, Post, PostStatus, RemovalSource
from src.models.profile import Profile
from tests.support_social import draft_post, guard, make_insight, make_member  # noqa: F401


async def put(member, insight, **body):
    return await member.http.put(f"/insights/{insight.insight_id}/post", json=body)


async def posts(db) -> list[Post]:
    return list(
        (
            await db.scalars(
                select(Post).order_by(Post.id).execution_options(populate_existing=True)
            )
        ).all()
    )


async def test_it_makes_one_public_post_with_no_reflection_and_repeats_as_the_same_post(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    insight = make_insight(member)

    first = await put(member, insight)
    second = await put(member, insight)

    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["status"], body["visibility"], body["reflection"]) == ("published", "public", None)
    assert second.json()["id"] == body["id"]
    assert len(await posts(db_session)) == 1
    assert guard.texts == []


async def test_a_draft_of_the_insight_is_submitted_and_returned(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    insight = make_insight(member)
    draft = (await draft_post(member, insight)).json()
    assert draft["status"] == "draft"

    response = await put(member, insight)

    assert response.json()["id"] == draft["id"]
    assert response.json()["status"] == "published"
    assert len(await posts(db_session)) == 1


async def test_a_post_that_is_not_live_is_returned_as_it_is_never_replaced(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    insight = make_insight(member)
    created = (await put(member, insight)).json()
    for state in (PostStatus.REMOVED, PostStatus.REJECTED, PostStatus.PENDING_REVIEW):
        post = (await posts(db_session))[0]
        post.status = state
        if state is PostStatus.REMOVED:
            post.removal_source = RemovalSource.MODERATOR
        await db_session.flush()

        again = await put(member, insight)

        assert again.status_code == 200, again.text
        assert again.json()["id"] == created["id"]
        assert again.json()["status"] == state.value
        assert len(await posts(db_session)) == 1


async def test_after_the_author_withdraws_a_new_call_makes_a_new_post(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    insight = make_insight(member)
    first = (await put(member, insight)).json()["id"]
    assert (await member.http.delete(f"/posts/{first}")).status_code in (200, 204)

    second = await put(member, insight)

    assert second.status_code == 200, second.text
    assert second.json()["id"] != first
    assert second.json()["status"] == "published"
    assert len(await posts(db_session)) == 2


async def test_a_member_without_a_handle_is_asked_for_one(make_member, make_insight, guard):
    member = await make_member("amal", identity=False)

    response = await put(member, make_insight(member))

    assert response.status_code == 409
    assert response.json()["error"] == "PUBLIC_IDENTITY_REQUIRED"


async def test_someone_elses_insight_is_not_found(make_member, make_insight, guard):
    owner = await make_member("amal")
    other = await make_member("bilal")

    response = await put(other, make_insight(owner))

    assert response.status_code == 404


async def test_the_photo_is_shown_only_when_the_photo_rules_allow_it(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    refused = make_insight(member, photo_ref="private/a.jpg", photo_consent=False)
    assert (await put(member, refused, photo=True)).status_code == 200
    profile = await db_session.get(Profile, member.user.id)
    profile.photo_storage_consent = True
    await db_session.flush()
    allowed = make_insight(member, photo_ref="private/b.jpg", photo_consent=True)
    assert (await put(member, allowed, photo=True)).status_code == 200

    refs = {
        row.insight_id: row.photo_ref
        for row in (await db_session.scalars(select(InsightPublication))).all()
    }

    assert refs[refused.insight_id] is None
    assert refs[allowed.insight_id] == "private/b.jpg"
    assert await db_session.scalar(select(func.count()).select_from(Post)) == 2


async def test_creating_a_post_of_an_insight_with_an_unsent_post_replaces_it(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    insight = make_insight(member)
    first = (await draft_post(member, insight, reflection="one")).json()
    again = await draft_post(member, insight, reflection="two", visibility="followers")
    assert again.status_code == 201, again.text
    assert again.json()["id"] != first["id"]
    assert again.json()["reflection"]["text"] == "two"
    (old, new) = await posts(db_session)
    assert (old.status, new.status) == (PostStatus.REMOVED, PostStatus.DRAFT)
    new.status = PostStatus.REJECTED
    await db_session.flush()

    third = await draft_post(member, insight, reflection="three")

    assert (third.status_code, third.json()["status"]) == (201, "draft")
    assert len(await posts(db_session)) == 3


async def test_creating_a_second_post_of_a_live_one_is_refused_until_it_is_withdrawn(
    db_session, make_member, make_insight, guard
):
    member = await make_member("amal")
    insight = make_insight(member)
    first = (await put(member, insight)).json()["id"]
    for state in (PostStatus.PUBLISHED, PostStatus.PENDING_REVIEW, PostStatus.REMOVED):
        post = (await posts(db_session))[0]
        post.status = state
        if state is PostStatus.REMOVED:
            post.removal_source = RemovalSource.MODERATOR
        await db_session.flush()

        refused = await draft_post(member, insight)

        assert (refused.status_code, refused.json()["error"]) == (409, "INSIGHT_ALREADY_POSTED")
    post = (await posts(db_session))[0]
    post.status = PostStatus.PUBLISHED
    await db_session.flush()
    assert (await member.http.delete(f"/posts/{first}")).status_code in (200, 204)

    fresh = await draft_post(member, insight)

    assert fresh.status_code == 201
    assert fresh.json()["id"] != first
