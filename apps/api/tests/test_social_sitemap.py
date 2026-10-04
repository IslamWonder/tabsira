"""The posts and profiles sections of the sitemap: only what a stranger may read, and nothing else."""

from __future__ import annotations

from sqlalchemy import text

from src.services import sitemap_service
from src.services.sitemap_service import Section
from src.services.social_sitemap import post_path, profile_path
from tests.support_social import ALLOW, REVIEW, draft_post, publish_post


async def paths(guest, section, page=0):
    response = await guest.http.get(f"/sitemap/{section}", params={"page": page})
    assert response.status_code == 200
    return [entry["path"] for entry in response.json()]


async def test_the_providers_are_registered_for_their_sections():
    from src.services.social_sitemap import PostsProvider, ProfilesProvider

    assert isinstance(sitemap_service.PROVIDERS[Section.POSTS], PostsProvider)
    assert isinstance(sitemap_service.PROVIDERS[Section.PROFILES], ProfilesProvider)


async def test_only_public_published_posts_of_live_authors_are_listed_oldest_first(
    make_member, make_insight, guard, db_session
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    guest = await make_member(signed_in=False)
    first = await publish_post(ann, make_insight)
    await publish_post(ann, make_insight, visibility="followers")
    withdrawn = await publish_post(ann, make_insight)
    await ann.http.delete(f"/posts/{withdrawn}")
    await draft_post(ann, make_insight(ann))
    guard.verdict = REVIEW
    held = (await draft_post(ann, make_insight(ann), reflection="x")).json()["id"]
    await ann.http.post(f"/posts/{held}/submit")
    guard.verdict = ALLOW
    second = await publish_post(bob, make_insight)
    hidden = await publish_post(bob, make_insight)
    await db_session.execute(
        text(
            "UPDATE app.posts SET status = 'removed', removal_source = 'moderator' WHERE id = :id"
        ),
        {"id": int(hidden)},
    )

    assert await paths(guest, "posts") == [post_path(int(first)), post_path(int(second))]


async def test_a_post_leaves_the_list_the_moment_it_is_withdrawn_or_its_author_is_disabled(
    make_member, make_insight, guard, db_session
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    guest = await make_member(signed_in=False)
    one = await publish_post(ann, make_insight)
    await publish_post(bob, make_insight)

    await ann.http.delete(f"/posts/{one}")
    bob.user.is_active = False
    await db_session.flush()

    assert await paths(guest, "posts") == []
    assert await paths(guest, "profiles") == []


async def test_the_pages_are_cut_by_the_page_size_with_the_records_own_change_time(
    make_member, make_insight, guard, account_app, account_settings, db_session
):
    account_app.state.settings = account_settings.model_copy(update={"sitemap_page_size": 2})
    ann = await make_member("ann")
    guest = await make_member(signed_in=False)
    ids = [int(await publish_post(ann, make_insight)) for _ in range(3)]
    await db_session.execute(
        text("UPDATE app.posts SET updated_at = '2026-03-01T00:00:00Z' WHERE id = :id"),
        {"id": ids[0]},
    )
    await db_session.execute(
        text("UPDATE app.posts SET updated_at = '2026-05-01T00:00:00Z' WHERE id = :id"),
        {"id": ids[2]},
    )

    index = (await guest.http.get("/sitemap")).json()["sections"]["posts"]

    assert [page["page"] for page in index] == [0, 1]
    assert index[1]["lastmod"] == "2026-05-01T00:00:00Z"
    assert await paths(guest, "posts", 0) == [post_path(ids[0]), post_path(ids[1])]
    assert await paths(guest, "posts", 1) == [post_path(ids[2])]
    assert await paths(guest, "posts", 2) == []


async def test_a_profile_is_listed_only_with_a_public_post_and_its_handle_is_percent_encoded(
    make_member, make_insight, guard
):
    arabic = await make_member("نور")
    await make_member("quiet")
    private_only = await make_member("private")
    guest = await make_member(signed_in=False)
    await publish_post(arabic, make_insight)
    await publish_post(private_only, make_insight, visibility="followers")

    listed = await paths(guest, "profiles")

    assert listed == ["/u/%D9%86%D9%88%D8%B1"]
    assert profile_path("Basira_1") == "/u/Basira_1"
    entries = (await guest.http.get("/sitemap/profiles")).json()
    assert entries[0]["lastmod"] is not None and entries[0]["images"] == []


async def test_a_profile_pages_use_the_newest_change_of_the_account_or_its_posts(
    make_member, make_insight, guard, db_session
):
    ann = await make_member("ann")
    guest = await make_member(signed_in=False)
    await publish_post(ann, make_insight)
    await db_session.execute(
        text("UPDATE app.users SET updated_at = '2026-02-01T00:00:00Z' WHERE handle = 'ann'")
    )
    await db_session.execute(text("UPDATE app.posts SET updated_at = '2026-04-01T00:00:00Z'"))

    index = (await guest.http.get("/sitemap")).json()["sections"]["profiles"]

    assert index == [{"page": 0, "lastmod": "2026-04-01T00:00:00Z"}]


async def test_nothing_of_the_network_is_listed_while_its_feature_is_off(
    make_member, make_insight, guard, account_app, account_settings
):
    ann = await make_member("ann")
    guest = await make_member(signed_in=False)
    await publish_post(ann, make_insight)
    account_app.state.settings = account_settings.model_copy(update={"feature_social": False})

    index = (await guest.http.get("/sitemap")).json()["sections"]

    assert "posts" not in index and "profiles" not in index
    assert (await guest.http.get("/sitemap/posts")).status_code == 404
