"""The account export and deletion cover everything the account wrote and did on the network."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from src.models import (
    Block,
    Bookmark,
    Comment,
    Follow,
    InsightPublication,
    ModerationAction,
    Post,
    PostLike,
    Report,
    User,
)
from tests.support_social import draft_post, publish_post


async def test_the_export_holds_the_posts_comments_and_everything_done_on_the_network(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    published = await publish_post(ann, make_insight, reflection="تأملي المنشور")
    draft = (await draft_post(ann, make_insight(ann), reflection="مسودتي")).json()["id"]
    theirs = await publish_post(bob, make_insight)
    await ann.http.put("/u/bob/follow")
    await ann.http.put(f"/posts/{theirs}/like")
    await ann.http.put(f"/posts/{theirs}/bookmark")
    comment = (await ann.http.post(f"/posts/{theirs}/comments", json={"body": "تعليقي"})).json()[
        "id"
    ]
    await ann.http.post(
        "/reports",
        json={
            "target_type": "post",
            "target_id": theirs,
            "reason": "wrong_place",
            "details": "خطأ",
        },
    )
    await ann.http.put("/blocks/bob")

    response = await ann.http.get("/account/export")

    social = response.json()["social"]
    assert response.status_code == 200
    assert {p["id"]: p["status"] for p in social["posts"]} == {
        published: "published",
        draft: "draft",
    }
    mine = next(p for p in social["posts"] if p["id"] == published)
    assert mine["reflection"] == "تأملي المنشور"
    assert mine["publication"]["title"] == "ماء يجري"
    assert mine["publication"]["quran_refs"] == [{"surah": 112, "ayah": 1}]
    assert mine["publication"]["hadith_refs"] == [{"collection": "bukhari", "number": "1"}]
    assert [(c["id"], c["body"], c["post_id"]) for c in social["comments"]] == [
        (comment, "تعليقي", theirs)
    ]
    # The block ended the follow.
    assert social["following"] == []
    assert [b["handle"] for b in social["blocked"]] == ["bob"]
    assert [m["post_id"] for m in social["likes"]] == [theirs]
    assert [m["post_id"] for m in social["bookmarks"]] == [theirs]
    assert [(r["target_id"], r["reason"], r["details"]) for r in social["reports"]] == [
        (theirs, "wrong_place", "خطأ")
    ]


async def test_the_export_lists_who_the_account_follows_by_handle_only(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    await make_member("bob")
    await ann.http.put("/u/bob/follow")

    social = (await ann.http.get("/account/export")).json()["social"]

    assert [f["handle"] for f in social["following"]] == ["bob"]
    assert set(social["following"][0]) == {"handle", "since"}


async def test_the_export_carries_the_public_identity_and_ids_as_strings(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    post_id = await publish_post(ann, make_insight)

    body = (await ann.http.get("/account/export")).json()

    assert (body["user"]["handle"], body["user"]["public_name"]) == ("ann", "ann name")
    assert body["social"]["posts"][0]["id"] == post_id
    assert isinstance(body["social"]["posts"][0]["id"], str)


async def test_the_export_is_only_about_the_caller_and_never_names_another_account(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    await publish_post(bob, make_insight, reflection="خاص ببوب")
    await bob.http.put("/u/ann/follow")

    text_ = (await ann.http.get("/account/export")).text

    social = json.loads(text_)["social"]
    assert social["posts"] == [] and social["following"] == [] and social["comments"] == []
    assert "خاص ببوب" not in text_
    assert str(bob.user.id) not in text_
    assert "bob@example.com" not in text_


async def test_deleting_the_account_removes_every_post_comment_and_reaction_and_nothing_of_others(
    make_member, make_insight, guard, db_session
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    mine = await publish_post(ann, make_insight, reflection="تأملي")
    theirs = await publish_post(bob, make_insight)
    await ann.http.put("/u/bob/follow")
    await ann.http.put(f"/posts/{theirs}/like")
    await ann.http.put(f"/posts/{theirs}/bookmark")
    await ann.http.post(f"/posts/{theirs}/comments", json={"body": "تعليقي"})
    await bob.http.post(f"/posts/{mine}/comments", json={"body": "رد بوب"})
    await bob.http.put(f"/posts/{mine}/like")
    await ann.http.post(
        "/reports", json={"target_type": "post", "target_id": theirs, "reason": "spam"}
    )
    await bob.http.put("/blocks/ann")
    guest = await make_member(signed_in=False)

    response = await ann.http.delete("/account")

    assert response.status_code == 204
    assert (await guest.http.get(f"/posts/{mine}")).status_code == 404
    assert (await guest.http.get("/u/ann")).status_code == 404
    for model in (Follow, Block, PostLike, Bookmark, Report):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0, model
    posts = (await db_session.scalars(select(Post))).all()
    assert [p.id for p in posts] == [int(theirs)]
    assert await db_session.scalar(select(func.count()).select_from(InsightPublication)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Comment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    # The moderation log holds no text and no author, so it outlives the account untouched.
    assert await db_session.scalar(select(func.count()).select_from(ModerationAction)) >= 2
    assert (await guest.http.get(f"/posts/{theirs}")).json()["comment_count"] == 0
