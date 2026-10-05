"""Reactions («انتفعتُ بها», «جزاك الله خيرًا») and bookmarks: one each, safe to repeat, and only on what the caller may read."""

from __future__ import annotations

from sqlalchemy import func, select

from src.models import Bookmark, PostReaction
from src.services.social_limits import SocialLimits, WriteKind
from tests.helpers import any_id
from tests.support_social import draft_post, publish_post


async def count(db_session, model):
    return await db_session.scalar(select(func.count()).select_from(model))


# ─── Reactions ────────────────────────────────────────────────────────────────

NONE = {"benefited": 0, "jazak": 0}


async def test_a_reaction_is_one_per_kind_and_account_and_counts_are_read_from_the_rows(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    one = await make_member("one")
    two = await make_member("two")
    post_id = await publish_post(author, make_insight)

    first = await one.http.put(f"/posts/{post_id}/reactions/benefited")
    again = await one.http.put(f"/posts/{post_id}/reactions/benefited")
    jazak = await one.http.put(f"/posts/{post_id}/reactions/jazak")
    other = await two.http.put(f"/posts/{post_id}/reactions/benefited")

    assert first.json() == {"reactions": {"benefited": 1, "jazak": 0}, "mine": ["benefited"]}
    assert again.json() == first.json()
    assert jazak.json() == {
        "reactions": {"benefited": 1, "jazak": 1},
        "mine": ["benefited", "jazak"],
    }
    assert other.json() == {"reactions": {"benefited": 2, "jazak": 1}, "mine": ["benefited"]}
    assert await count(db_session, PostReaction) == 3
    seen = (await one.http.get(f"/posts/{post_id}")).json()
    assert seen["reactions"] == {"benefited": 2, "jazak": 1}
    assert seen["viewer"]["reactions"] == ["benefited", "jazak"]
    by_author = (await author.http.get(f"/posts/{post_id}")).json()
    assert (by_author["reactions"], by_author["viewer"]["reactions"]) == (
        {"benefited": 2, "jazak": 1},
        [],
    )
    assert (await guest_get(make_member, post_id))["reactions"] == {"benefited": 2, "jazak": 1}


async def guest_get(make_member, post_id):
    guest = await make_member(signed_in=False)
    return (await guest.http.get(f"/posts/{post_id}")).json()


async def test_taking_back_a_reaction_is_safe_to_repeat_and_keeps_the_others(
    make_member, make_insight, guard
):
    author = await make_member("author")
    one = await make_member("one")
    two = await make_member("two")
    post_id = await publish_post(author, make_insight)
    await one.http.put(f"/posts/{post_id}/reactions/benefited")
    await one.http.put(f"/posts/{post_id}/reactions/jazak")
    await two.http.put(f"/posts/{post_id}/reactions/benefited")

    first = await one.http.delete(f"/posts/{post_id}/reactions/benefited")
    again = await one.http.delete(f"/posts/{post_id}/reactions/benefited")

    assert first.json() == {"reactions": {"benefited": 1, "jazak": 1}, "mine": ["jazak"]}
    assert again.json() == first.json()
    last = await one.http.delete(f"/posts/{post_id}/reactions/jazak")
    assert last.json() == {"reactions": {"benefited": 1, "jazak": 0}, "mine": []}


async def test_a_post_with_no_reaction_says_zero_and_the_old_like_routes_are_gone(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)

    seen = (await reader.http.get(f"/posts/{post_id}")).json()

    assert seen["reactions"] == NONE
    assert seen["viewer"]["reactions"] == []
    assert "like_count" not in seen
    assert (await reader.http.put(f"/posts/{post_id}/like")).status_code == 404
    assert (await reader.http.delete(f"/posts/{post_id}/like")).status_code == 404


async def test_a_reaction_needs_a_verified_session_and_a_post_the_caller_may_read(
    make_member, make_insight, guard
):
    author = await make_member("author")
    guest = await make_member(signed_in=False)
    unverified = await make_member("fresh", verified=False)
    stranger = await make_member("stranger")
    public_id = await publish_post(author, make_insight)
    private_id = await publish_post(author, make_insight, visibility="followers")

    def route(post_id: object, kind: str = "jazak") -> str:
        return f"/posts/{post_id}/reactions/{kind}"

    assert (await guest.http.put(route(public_id))).status_code == 401
    assert (await guest.http.delete(route(public_id))).status_code == 401
    assert (await unverified.http.put(route(public_id))).status_code == 403
    assert (await stranger.http.put(route(private_id))).status_code == 404
    assert (await stranger.http.put(route(any_id()))).status_code == 404
    assert (await stranger.http.put(route(0))).status_code == 422
    assert (await stranger.http.put(route(2**63))).status_code == 422
    assert (await stranger.http.put(route(public_id, "like"))).status_code == 422
    assert (await stranger.http.delete(route(public_id, "like"))).status_code == 422


async def test_a_post_that_is_not_published_takes_no_reaction_even_from_its_author(
    make_member, make_insight, guard
):
    author = await make_member("author")
    post_id = (await draft_post(author, make_insight(author))).json()["id"]

    response = await author.http.put(f"/posts/{post_id}/reactions/jazak")

    assert (response.status_code, response.json()["error"]) == (409, "CONFLICT")


async def test_nobody_reacts_across_a_block_or_to_a_post_that_is_gone(
    make_member, make_insight, guard
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    await reader.http.put(f"/posts/{post_id}/reactions/jazak")
    await author.http.put("/blocks/reader")

    assert (await reader.http.put(f"/posts/{post_id}/reactions/jazak")).status_code == 404
    assert (await reader.http.delete(f"/posts/{post_id}/reactions/jazak")).status_code == 404
    assert (await reader.http.put(f"/posts/{post_id}/bookmark")).status_code == 404
    await author.http.delete("/blocks/reader")
    await author.http.delete(f"/posts/{post_id}")
    assert (await reader.http.put(f"/posts/{post_id}/reactions/jazak")).status_code == 410
    assert (await reader.http.delete(f"/posts/{post_id}/reactions/jazak")).status_code == 410


async def test_reactions_are_rate_limited_per_account(
    make_member, make_insight, guard, account_app
):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    account_app.state.social_limits = SocialLimits({WriteKind.REACTION: (1, 100, 60)})

    first = await reader.http.put(f"/posts/{post_id}/reactions/benefited")
    second = await reader.http.put(f"/posts/{post_id}/reactions/jazak")

    assert (first.status_code, second.status_code) == (200, 429)


# ─── Bookmarks ────────────────────────────────────────────────────────────────


async def test_a_bookmark_is_private_idempotent_and_listed_latest_first_in_pages(
    make_member, make_insight, guard, db_session
):
    author = await make_member("author")
    reader = await make_member("reader")
    ids = [await publish_post(author, make_insight) for _ in range(3)]
    for post_id in ids:
        assert (await reader.http.put(f"/posts/{post_id}/bookmark")).status_code == 204
    assert (await reader.http.put(f"/posts/{ids[0]}/bookmark")).status_code == 204
    assert await count(db_session, Bookmark) == 3

    first = (await reader.http.get("/me/bookmarks", params={"limit": 2})).json()
    second = (
        await reader.http.get("/me/bookmarks", params={"limit": 2, "cursor": first["next_cursor"]})
    ).json()

    assert [item["id"] for item in first["items"]] == [ids[2], ids[1]]
    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None
    assert all(item["viewer"]["bookmarked"] for item in first["items"])
    # Nobody else sees them, and no response of a post says how many saved it.
    assert (await author.http.get("/me/bookmarks")).json()["items"] == []
    body = (await author.http.get(f"/posts/{ids[0]}")).text
    assert "bookmark_count" not in body
    assert (await reader.http.get("/me/bookmarks")).json()["empty_reason"] is None


async def test_unsaving_is_safe_to_repeat(make_member, make_insight, guard, db_session):
    author = await make_member("author")
    reader = await make_member("reader")
    post_id = await publish_post(author, make_insight)
    await reader.http.put(f"/posts/{post_id}/bookmark")

    assert (await reader.http.delete(f"/posts/{post_id}/bookmark")).status_code == 204
    assert (await reader.http.delete(f"/posts/{post_id}/bookmark")).status_code == 204
    assert await count(db_session, Bookmark) == 0
    assert (await reader.http.delete(f"/posts/{any_id()}/bookmark")).status_code == 204


async def test_a_saved_post_that_goes_away_leaves_the_list(make_member, make_insight, guard):
    author = await make_member("author")
    reader = await make_member("reader")
    gone = await publish_post(author, make_insight)
    blocked = await publish_post(author, make_insight)
    kept = await publish_post(author, make_insight)
    for post_id in (gone, blocked, kept):
        await reader.http.put(f"/posts/{post_id}/bookmark")
    await author.http.delete(f"/posts/{gone}")

    listed = [item["id"] for item in (await reader.http.get("/me/bookmarks")).json()["items"]]
    assert listed == [kept, blocked]
    await reader.http.put("/blocks/author")
    assert (await reader.http.get("/me/bookmarks")).json()["items"] == []


async def test_an_empty_bookmark_list_says_so_and_a_forged_cursor_is_refused(make_member):
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)

    empty = (await reader.http.get("/me/bookmarks")).json()
    bad = await reader.http.get("/me/bookmarks", params={"cursor": "forged"})

    assert empty == {"items": [], "next_cursor": None, "empty_reason": "no_posts"}
    assert bad.json()["error"] == "INVALID_CURSOR"
    assert (await guest.http.get("/me/bookmarks")).status_code == 401
    assert (await guest.http.put(f"/posts/{any_id()}/bookmark")).status_code == 401
