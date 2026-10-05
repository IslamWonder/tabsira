"""The feeds: what is in them, in what order, and what is never in them."""

from __future__ import annotations

import pytest

from src.features import FeatureFlag
from src.services import feed_service
from tests.helpers import switched
from tests.support_social import REVIEW, draft_post, publish_post


@pytest.fixture
def account_settings(account_settings):
    """These tests write and read comments, which are off until the owners enable them."""
    return switched(account_settings, on=[FeatureFlag.SOCIAL_COMMENTS])


async def ids(response):
    return [item["id"] for item in response.json()["items"]]


async def feed(member, name, **params):
    return await member.http.get(f"/feed/{name}", params=params)


# ─── The latest ───────────────────────────────────────────────────────────────


async def test_the_latest_lists_every_public_post_newest_first_to_anyone(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    guest = await make_member(signed_in=False)
    first = await publish_post(ann, make_insight)
    second = await publish_post(bob, make_insight)
    third = await publish_post(ann, make_insight)

    response = await feed(guest, "latest")

    assert response.status_code == 200
    assert await ids(response) == [third, second, first]
    assert response.json()["next_cursor"] is None
    assert response.json()["empty_reason"] is None
    assert all(item["why"] is None for item in response.json()["items"])


async def test_the_latest_never_lists_a_post_that_is_not_public_published_and_live(
    make_member, make_insight, guard, db_session
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    guest = await make_member(signed_in=False)
    shown = await publish_post(ann, make_insight)
    await publish_post(ann, make_insight, visibility="followers")
    withdrawn = await publish_post(ann, make_insight)
    await ann.http.delete(f"/posts/{withdrawn}")
    await draft_post(ann, make_insight(ann))
    guard.verdict = REVIEW
    held = (await draft_post(ann, make_insight(ann), reflection="x")).json()["id"]
    await ann.http.post(f"/posts/{held}/submit")
    gone = await publish_post(bob, make_insight)
    bob.user.is_active = False
    await db_session.flush()

    assert await ids(await feed(guest, "latest")) == [shown]
    assert gone not in await ids(await feed(guest, "latest"))


async def test_the_latest_pages_by_cursor_and_a_new_post_does_not_repeat_or_skip_an_item(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    guest = await make_member(signed_in=False)
    posts = [await publish_post(ann, make_insight) for _ in range(5)]

    first = (await feed(guest, "latest", limit=2)).json()
    newcomer = await publish_post(ann, make_insight)
    second = (await feed(guest, "latest", limit=2, cursor=first["next_cursor"])).json()
    third = (await feed(guest, "latest", limit=2, cursor=second["next_cursor"])).json()

    assert [i["id"] for i in first["items"]] == [posts[4], posts[3]]
    assert [i["id"] for i in second["items"]] == [posts[2], posts[1]]
    assert [i["id"] for i in third["items"]] == [posts[0]]
    assert third["next_cursor"] is None
    assert newcomer not in [i["id"] for page in (second, third) for i in page["items"]]


async def test_a_post_withdrawn_between_two_pages_is_skipped_and_nothing_else_moves(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    guest = await make_member(signed_in=False)
    posts = [await publish_post(ann, make_insight) for _ in range(4)]

    first = (await feed(guest, "latest", limit=2)).json()
    await ann.http.delete(f"/posts/{posts[1]}")
    second = (await feed(guest, "latest", limit=2, cursor=first["next_cursor"])).json()

    assert [i["id"] for i in second["items"]] == [posts[0]]


async def test_a_blocked_author_is_in_no_feed_in_either_direction(make_member, make_insight, guard):
    ann = await make_member("ann")
    bob = await make_member("bob")
    carol = await make_member("carol")
    from_ann = await publish_post(ann, make_insight)
    from_bob = await publish_post(bob, make_insight)
    from_carol = await publish_post(carol, make_insight)

    await ann.http.put("/blocks/bob")

    assert await ids(await feed(ann, "latest")) == [from_carol, from_ann]
    assert await ids(await feed(bob, "latest")) == [from_carol, from_bob]
    assert await ids(await feed(carol, "latest")) == [from_carol, from_bob, from_ann]
    assert await ids(await feed(ann, "for-you")) == [from_carol]
    assert await ids(await feed(bob, "for-you")) == [from_carol]


async def test_an_empty_feed_says_so_and_nothing_is_invented(make_member):
    guest = await make_member(signed_in=False)

    for name in ("latest", "for-you"):
        body = (await feed(guest, name)).json()
        assert body == {"items": [], "next_cursor": None, "empty_reason": "no_posts"}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"limit": "x"}])
async def test_the_page_size_is_bounded(make_member, params):
    guest = await make_member(signed_in=False)

    assert (await feed(guest, "latest", **params)).status_code == 422


async def test_a_forged_cursor_is_refused_by_every_feed(make_member):
    reader = await make_member("reader")

    for name in ("latest", "for-you", "following"):
        response = await feed(reader, name, cursor="forged")
        assert (response.status_code, response.json()["error"]) == (400, "INVALID_CURSOR")


# ─── «أتابع» ──────────────────────────────────────────────────────────────────


async def test_following_needs_a_session(make_member):
    guest = await make_member(signed_in=False)

    assert (await feed(guest, "following")).status_code == 401


async def test_following_lists_the_followed_including_their_followers_only_posts_and_no_one_else(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    carol = await make_member("carol")
    await ann.http.put("/u/bob/follow")
    public = await publish_post(bob, make_insight)
    private = await publish_post(bob, make_insight, visibility="followers")
    await publish_post(carol, make_insight)
    await publish_post(ann, make_insight)

    response = await feed(ann, "following")

    assert await ids(response) == [private, public]
    assert response.json()["empty_reason"] is None


async def test_following_says_why_it_is_empty(make_member, make_insight, guard):
    ann = await make_member("ann")
    bob = await make_member("bob")

    nobody = (await feed(ann, "following")).json()
    await ann.http.put("/u/bob/follow")
    quiet = (await feed(ann, "following")).json()
    await publish_post(bob, make_insight)
    busy = (await feed(ann, "following")).json()

    assert nobody["empty_reason"] == "follows_nobody"
    assert quiet["empty_reason"] == "no_posts"
    assert busy["empty_reason"] is None


async def test_following_pages_by_cursor_and_a_block_removes_the_author(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    await ann.http.put("/u/bob/follow")
    posts = [await publish_post(bob, make_insight) for _ in range(3)]

    first = (await feed(ann, "following", limit=2)).json()
    second = (await feed(ann, "following", limit=2, cursor=first["next_cursor"])).json()
    await ann.http.put("/blocks/bob")

    assert [i["id"] for i in first["items"] + second["items"]] == posts[::-1]
    assert (await feed(ann, "following")).json()["items"] == []


# ─── «لك» ─────────────────────────────────────────────────────────────────────


async def test_for_you_explains_every_item_and_leaves_out_the_readers_own_posts(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    mine = await publish_post(ann, make_insight)
    theirs = await publish_post(bob, make_insight)

    body = (await feed(ann, "for-you")).json()

    assert [item["id"] for item in body["items"]] == [theirs]
    assert mine not in [item["id"] for item in body["items"]]
    assert body["items"][0]["why"] == {"code": "fresh", "text": "بصيرة نُشرت قبل قليل"}


async def test_for_you_lifts_a_followed_author_and_names_them(make_member, make_insight, guard):
    ann = await make_member("ann")
    bob = await make_member("bob")
    carol = await make_member("carol")
    older = await publish_post(bob, make_insight)
    newer = await publish_post(carol, make_insight)
    before = await ids(await feed(ann, "for-you"))
    await ann.http.put("/u/bob/follow")

    after = (await feed(ann, "for-you")).json()

    assert before == [newer, older]
    assert [i["id"] for i in after["items"]] == [older, newer]
    assert after["items"][0]["why"] == {"code": "followed_author", "text": "لأنك تتابع bob name"}


async def test_switching_personalisation_off_removes_the_follow_lift_and_the_met_penalty(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    carol = await make_member("carol")
    older = await publish_post(bob, make_insight)
    newer = await publish_post(carol, make_insight)
    await ann.http.put("/u/bob/follow")
    await ann.http.put(f"/posts/{newer}/like")
    personal = await ids(await feed(ann, "for-you"))

    await ann.http.post(
        "/consents", json={"kind": "personalization", "version": "v1", "granted": False}
    )
    plain = (await feed(ann, "for-you")).json()

    assert personal == [older, newer]
    assert [i["id"] for i in plain["items"]] == [newer, older]
    assert all(i["why"]["code"] != "followed_author" for i in plain["items"])


async def test_a_post_the_reader_already_liked_saved_or_commented_on_sinks(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    posts = [await publish_post(bob, make_insight) for _ in range(4)]
    await ann.http.put(f"/posts/{posts[3]}/like")
    await ann.http.put(f"/posts/{posts[2]}/bookmark")
    await ann.http.post(f"/posts/{posts[1]}/comments", json={"body": "x"})

    assert await ids(await feed(ann, "for-you")) == [posts[0], posts[3], posts[2], posts[1]]


async def test_for_you_mixes_topics_instead_of_repeating_one(make_member, make_insight, guard):
    ann = await make_member("ann")
    bob = await make_member("bob")
    water = [await publish_post_with(bob, make_insight, ("water",)) for _ in range(3)]
    light = await publish_post_with(bob, make_insight, ("light",))

    listed = await ids(await feed(ann, "for-you"))

    # The newest is a light post; it must not be pushed below all three water posts, and the
    # three water posts cannot all sit above it.
    assert listed[0] == light
    assert listed.index(light) < listed.index(water[0])


async def publish_post_with(member, make_insight, concepts):
    post_id = (await draft_post(member, make_insight(member, concepts=concepts))).json()["id"]
    await member.http.post(f"/posts/{post_id}/submit")
    return post_id


async def test_for_you_continues_the_same_list_across_pages_even_when_a_post_arrives(
    make_member, make_insight, guard
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    posts = [await publish_post(bob, make_insight) for _ in range(5)]

    first = (await feed(ann, "for-you", limit=2)).json()
    newcomer = await publish_post(bob, make_insight)
    second = (await feed(ann, "for-you", limit=2, cursor=first["next_cursor"])).json()
    third = (await feed(ann, "for-you", limit=2, cursor=second["next_cursor"])).json()

    seen = [i["id"] for page in (first, second, third) for i in page["items"]]
    assert seen == posts[::-1]
    assert newcomer not in seen
    assert third["next_cursor"] is None
    fresh = await ids(await feed(ann, "for-you", limit=2))
    assert fresh[0] == newcomer


async def test_for_you_ranks_a_bounded_window_of_the_newest_posts(
    make_member, make_insight, guard, monkeypatch
):
    monkeypatch.setattr(feed_service, "CANDIDATES", 2)
    ann = await make_member("ann")
    bob = await make_member("bob")
    posts = [await publish_post(bob, make_insight) for _ in range(4)]

    listed = await ids(await feed(ann, "for-you"))

    assert sorted(listed) == sorted(posts[2:])


async def test_for_you_hides_what_the_reader_may_not_read(make_member, make_insight, guard):
    ann = await make_member("ann")
    bob = await make_member("bob")
    private = await publish_post(bob, make_insight, visibility="followers")
    public = await publish_post(bob, make_insight)

    assert await ids(await feed(ann, "for-you")) == [public]
    await ann.http.put("/u/bob/follow")
    assert sorted(await ids(await feed(ann, "for-you"))) == sorted([private, public])


async def test_for_you_works_for_a_guest_with_freshness_and_variety_only(
    make_member, make_insight, guard
):
    bob = await make_member("bob")
    guest = await make_member(signed_in=False)
    older = await publish_post(bob, make_insight)
    newer = await publish_post(bob, make_insight)

    body = (await feed(guest, "for-you")).json()

    assert [i["id"] for i in body["items"]] == [newer, older]
    assert body["items"][0]["viewer"] is None


# ─── A member's posts ─────────────────────────────────────────────────────────


async def test_a_members_posts_follow_the_audience_of_each_post(make_member, make_insight, guard):
    bob = await make_member("bob")
    follower = await make_member("follower")
    stranger = await make_member("stranger")
    guest = await make_member(signed_in=False)
    public = await publish_post(bob, make_insight)
    private = await publish_post(bob, make_insight, visibility="followers")
    await follower.http.put("/u/bob/follow")

    async def listed(who):
        return await ids(await who.http.get("/u/bob/posts"))

    assert await listed(guest) == [public]
    assert await listed(stranger) == [public]
    assert await listed(follower) == [private, public]
    assert await listed(bob) == [private, public]


async def test_a_members_posts_are_a_404_for_an_unknown_member_or_across_a_block(
    make_member, make_insight, guard
):
    bob = await make_member("bob")
    ann = await make_member("ann")
    await publish_post(bob, make_insight)
    await ann.http.put("/blocks/bob")

    assert (await ann.http.get("/u/bob/posts")).status_code == 404
    assert (await bob.http.get("/u/ann/posts")).status_code == 404
    assert (await ann.http.get("/u/nobody/posts")).status_code == 404


async def test_the_profile_counts_published_public_posts(make_member, make_insight, guard):
    bob = await make_member("bob")
    guest = await make_member(signed_in=False)
    await publish_post(bob, make_insight)
    await publish_post(bob, make_insight, visibility="followers")
    withdrawn = await publish_post(bob, make_insight)
    await bob.http.delete(f"/posts/{withdrawn}")

    assert (await guest.http.get("/u/bob")).json()["posts_count"] == 1


async def test_every_feed_answers_404_while_the_feature_is_off(
    make_member, account_app, account_settings
):
    reader = await make_member("reader")
    account_app.state.settings = account_settings.model_copy(update={"disabled_features": "social"})

    for path in (
        "/feed/latest",
        "/feed/for-you",
        "/feed/following",
        "/u/reader/posts",
        "/me/bookmarks",
    ):
        assert (await reader.http.get(path)).status_code == 404, path
