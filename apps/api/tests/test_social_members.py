"""The public identity, public profiles, follows and blocks."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from src.errors import AppError, ErrorCode
from src.models import Block, Follow, User
from src.schemas.social import MemberProfileOut
from src.services import public_identity
from src.services.social_limits import SocialLimits, WriteKind

# ─── The public identity ──────────────────────────────────────────────────────


async def test_an_account_has_no_public_identity_until_it_chooses_one(make_member):
    reader = await make_member(identity=False)

    response = await reader.http.get("/me/public-identity")

    assert response.status_code == 200
    assert response.json() == {"handle": None, "public_name": None}


async def test_the_identity_routes_need_a_session(make_member):
    guest = await make_member(signed_in=False)

    assert (await guest.http.get("/me/public-identity")).status_code == 401
    put = await guest.http.put("/me/public-identity", json={"handle": "abc", "public_name": "A"})
    assert put.status_code == 401


async def test_an_unverified_account_cannot_choose_a_public_identity(make_member):
    reader = await make_member(identity=False, verified=False)

    response = await reader.http.put(
        "/me/public-identity", json={"handle": "basira", "public_name": "Basira"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "EMAIL_NOT_VERIFIED"


async def test_a_verified_account_chooses_a_handle_and_name_and_never_uses_its_own_name(
    make_member, db_session
):
    reader = await make_member(identity=False, display_name="Real Person")

    response = await reader.http.put(
        "/me/public-identity", json={"handle": "  Nur_1 ", "public_name": "  نور   الدين "}
    )

    assert response.status_code == 200
    assert response.json() == {"handle": "Nur_1", "public_name": "نور الدين"}
    assert (await reader.http.get("/me/public-identity")).json() == response.json()
    stored = await db_session.scalar(select(User).where(User.id == reader.user.id))
    assert (stored.handle, stored.public_name, stored.display_name) == (
        "Nur_1",
        "نور الدين",
        "Real Person",
    )


@pytest.mark.parametrize(
    "handle",
    [
        "ab",
        "1abc",
        "_abc",
        "a b",
        "مَحمد",
        "admin",
        "TABSIRA",
        "تبصرة",
        "الإدارة",
        "a" * 31,
        "",
        # Anything that starts like the platform or its staff passes for them.
        "tabsira_help",
        "Admin2",
        "supportteam",
        "تبصرة_علي",
        "مشرف_عام",
    ],
)
async def test_a_handle_that_is_malformed_or_reserved_is_refused(make_member, handle):
    reader = await make_member(identity=False)

    response = await reader.http.put(
        "/me/public-identity", json={"handle": handle, "public_name": "Name"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert response.json()["fields"][0]["loc"][-1] == "handle"


@pytest.mark.parametrize(
    "name",
    ["", "a@b.co", "see https://x.example", "www.x.example", "<b>x</b>", "x" * 41, "a\u0007b"],
)
async def test_a_public_name_with_a_link_an_address_or_control_characters_is_refused(
    make_member, name
):
    reader = await make_member(identity=False)

    response = await reader.http.put(
        "/me/public-identity", json={"handle": "okay", "public_name": name}
    )

    assert response.status_code == 422
    assert response.json()["fields"][0]["loc"][-1] == "public_name"


async def test_a_handle_in_a_compatibility_form_is_stored_in_its_plain_form(make_member):
    reader = await make_member(identity=False)

    response = await reader.http.put(
        "/me/public-identity", json={"handle": "\uff46\uff55\uff4c\uff4c", "public_name": "Name"}
    )

    assert response.json()["handle"] == "full"


async def test_a_handle_is_taken_whatever_its_case_but_its_holder_may_change_its_case(make_member):
    first = await make_member("Basira")
    second = await make_member("other", identity=False)

    taken = await second.http.put(
        "/me/public-identity", json={"handle": "bAsIrA", "public_name": "Name"}
    )
    again = await first.http.put(
        "/me/public-identity", json={"handle": "BASIRA", "public_name": "New name"}
    )

    assert (taken.status_code, taken.json()["error"]) == (409, "HANDLE_TAKEN")
    assert again.status_code == 200
    assert again.json() == {"handle": "BASIRA", "public_name": "New name"}


async def test_losing_a_race_for_a_handle_is_a_conflict_and_not_a_crash(make_member, db_session):
    await make_member("racer")
    late = await make_member("late", identity=False)

    # The pre-check saw the handle free; the unique index still refuses the write.
    db_session.scalar = AsyncMock(return_value=None)
    with pytest.raises(AppError) as caught:
        await public_identity.set_public_identity(
            db_session, late.user, handle="RACER", public_name="Name"
        )

    assert caught.value.code is ErrorCode.HANDLE_TAKEN


async def test_a_member_is_found_by_handle_in_any_case_unless_disabled_or_deleted(
    make_member, db_session
):
    member = await make_member("Finder")

    assert (await public_identity.find_member(db_session, " fINDER ")).id == member.user.id
    member.user.is_active = False
    await db_session.flush()
    assert await public_identity.find_member(db_session, "finder") is None
    member.user.is_active = True
    member.user.deleted_at = func.now()
    await db_session.flush()
    assert await public_identity.find_member(db_session, "finder") is None


# ─── Public profiles ──────────────────────────────────────────────────────────


async def test_a_profile_is_public_and_says_only_what_the_member_chose(make_member):
    author = await make_member("author", display_name="Secret Real Name")
    guest = await make_member(signed_in=False)

    response = await guest.http.get("/u/AUTHOR")

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {
        "handle",
        "public_name",
        "joined_month",
        "posts_count",
        "followers_count",
        "following_count",
        "viewer",
    }
    assert (body["handle"], body["public_name"]) == ("author", "author name")
    assert body["joined_month"] == author.user.created_at.strftime("%Y-%m")
    assert (body["posts_count"], body["followers_count"], body["following_count"]) == (0, 0, 0)
    assert body["viewer"] is None
    for private in ("Secret Real Name", "author@example.com", str(author.user.id)):
        assert private not in response.text


def test_no_profile_field_could_hold_a_private_answer_an_address_or_a_place():
    names = set(MemberProfileOut.model_fields)

    assert not {n for n in names if "email" in n or "location" in n or "place" in n}
    assert not {"gender", "age_range", "religious_background", "goals", "display_name"} & names


async def test_a_profile_of_nobody_or_of_a_disabled_account_is_a_404(make_member, db_session):
    guest = await make_member(signed_in=False)
    gone = await make_member("gone")

    assert (await guest.http.get("/u/nobody")).status_code == 404
    gone.user.is_active = False
    await db_session.flush()
    assert (await guest.http.get("/u/gone")).status_code == 404


async def test_a_profile_counts_what_it_counts_and_tells_the_viewer_whether_they_follow(
    make_member,
):
    author = await make_member("author")
    fan = await make_member("fan")
    other = await make_member("other")
    await fan.http.put("/u/author/follow")
    await other.http.put("/u/author/follow")
    await author.http.put("/u/fan/follow")

    seen_by_fan = (await fan.http.get("/u/author")).json()
    seen_by_author = (await author.http.get("/u/author")).json()

    assert (seen_by_fan["followers_count"], seen_by_fan["following_count"]) == (2, 1)
    assert seen_by_fan["viewer"] == {"follows": True, "is_self": False}
    assert seen_by_author["viewer"] == {"follows": False, "is_self": True}


# ─── Follows ──────────────────────────────────────────────────────────────────


async def test_following_is_idempotent_and_unfollowing_is_safe_to_repeat(make_member, db_session):
    author = await make_member("author")
    fan = await make_member("fan")

    first = await fan.http.put("/u/author/follow")
    second = await fan.http.put("/u/author/follow")

    assert (first.status_code, second.status_code) == (204, 204)
    assert await db_session.scalar(select(func.count()).select_from(Follow)) == 1
    assert (await fan.http.delete("/u/author/follow")).status_code == 204
    assert (await fan.http.delete("/u/author/follow")).status_code == 204
    assert await db_session.scalar(select(func.count()).select_from(Follow)) == 0
    assert (await author.http.get("/u/author")).json()["followers_count"] == 0


async def test_nobody_follows_themselves_or_someone_who_does_not_exist(make_member):
    fan = await make_member("fan")

    own = await fan.http.put("/u/fan/follow")
    nobody = await fan.http.put("/u/nobody/follow")
    nobody_unfollow = await fan.http.delete("/u/nobody/follow")

    assert (own.status_code, own.json()["error"]) == (400, "BAD_REQUEST")
    assert nobody.status_code == 404
    assert nobody_unfollow.status_code == 404


async def test_following_needs_a_verified_session_and_unfollowing_a_session(make_member):
    await make_member("author")
    guest = await make_member(signed_in=False)
    unverified = await make_member("fresh", verified=False)

    assert (await guest.http.put("/u/author/follow")).status_code == 401
    assert (await guest.http.delete("/u/author/follow")).status_code == 401
    assert (await unverified.http.put("/u/author/follow")).status_code == 403
    assert (await unverified.http.delete("/u/author/follow")).status_code == 204


# ─── Blocks ───────────────────────────────────────────────────────────────────


async def test_a_block_ends_the_follows_in_both_directions_and_hides_both_profiles(
    make_member, db_session
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    await ann.http.put("/u/bob/follow")
    await bob.http.put("/u/ann/follow")

    blocked = await ann.http.put("/blocks/bob")

    assert blocked.status_code == 204
    assert await db_session.scalar(select(func.count()).select_from(Follow)) == 0
    assert (await ann.http.get("/u/bob")).status_code == 404
    assert (await bob.http.get("/u/ann")).status_code == 404
    assert (await bob.http.put("/u/ann/follow")).status_code == 404
    assert (await ann.http.put("/u/bob/follow")).status_code == 404
    # Someone else still sees both.
    carol = await make_member("carol")
    assert (await carol.http.get("/u/ann")).status_code == 200
    assert (await carol.http.get("/u/bob")).status_code == 200


async def test_blocking_twice_changes_nothing_and_lifting_restores_the_view_but_not_the_follows(
    make_member, db_session
):
    ann = await make_member("ann")
    bob = await make_member("bob")
    await ann.http.put("/u/bob/follow")
    await ann.http.put("/blocks/bob")
    await ann.http.put("/blocks/bob")

    assert await db_session.scalar(select(func.count()).select_from(Block)) == 1
    assert (await ann.http.delete("/blocks/bob")).status_code == 204
    assert (await ann.http.delete("/blocks/bob")).status_code == 204
    assert (await ann.http.get("/u/bob")).status_code == 200
    assert (await bob.http.get("/u/ann")).json()["followers_count"] == 0


async def test_only_the_blocker_can_lift_a_block(make_member, db_session):
    ann = await make_member("ann")
    bob = await make_member("bob")
    await ann.http.put("/blocks/bob")

    assert (await bob.http.delete("/blocks/ann")).status_code == 204

    assert await db_session.scalar(select(func.count()).select_from(Block)) == 1
    assert (await bob.http.get("/u/ann")).status_code == 404


async def test_the_block_list_names_only_handles_and_public_names(make_member):
    ann = await make_member("ann")
    await make_member("bob")
    await make_member("cyd")
    await ann.http.put("/blocks/bob")
    await ann.http.put("/blocks/cyd")

    body = (await ann.http.get("/blocks")).json()

    assert body == [
        {"handle": "cyd", "public_name": "cyd name"},
        {"handle": "bob", "public_name": "bob name"},
    ]


async def test_nobody_blocks_themselves_or_someone_who_does_not_exist_and_a_session_is_needed(
    make_member,
):
    ann = await make_member("ann")
    guest = await make_member(signed_in=False)

    assert (await ann.http.put("/blocks/ann")).json()["error"] == "BAD_REQUEST"
    assert (await ann.http.put("/blocks/nobody")).status_code == 404
    assert (await ann.http.delete("/blocks/nobody")).status_code == 404
    assert (await guest.http.get("/blocks")).status_code == 401
    assert (await guest.http.put("/blocks/ann")).status_code == 401


# ─── Limits and the feature flag ──────────────────────────────────────────────


async def test_follows_are_rate_limited_per_account_with_a_retry_after(make_member, account_app):
    account_app.state.social_limits = SocialLimits({WriteKind.REACTION: (2, 100, 60)})
    await make_member("author")
    fan = await make_member("fan")

    codes = [(await fan.http.put("/u/author/follow")).status_code for _ in range(3)]
    third = await fan.http.put("/u/author/follow")

    assert codes == [204, 204, 429]
    assert third.json()["error"] == "RATE_LIMITED"
    assert int(third.headers["retry-after"]) >= 1


async def test_the_identity_and_block_writes_have_their_own_budgets(make_member, account_app):
    account_app.state.social_limits = SocialLimits(
        {WriteKind.IDENTITY: (1, 100, 60), WriteKind.BLOCK: (1, 100, 60)}
    )
    ann = await make_member("ann")
    await make_member("bob")

    first = await ann.http.put("/me/public-identity", json={"handle": "anna", "public_name": "A"})
    second = await ann.http.put("/me/public-identity", json={"handle": "annb", "public_name": "A"})
    block = await ann.http.put("/blocks/bob")
    over = await ann.http.delete("/blocks/bob")

    assert [first.status_code, second.status_code] == [200, 429]
    assert [block.status_code, over.status_code] == [204, 429]


async def test_every_social_route_answers_404_while_the_feature_is_off(
    make_member, account_app, account_settings
):
    reader = await make_member("reader")
    # The identity stays open while the atlas is on (next test); here both are off.
    account_app.state.settings = account_settings.model_copy(
        update={"feature_social": False, "feature_atlas": False}
    )

    for method, path in (
        ("GET", "/me/public-identity"),
        ("GET", "/u/reader"),
        ("PUT", "/u/reader/follow"),
        ("GET", "/blocks"),
    ):
        response = await reader.http.request(method, path)
        assert response.status_code == 404, path


async def test_the_atlas_alone_opens_the_public_identity_and_nothing_else_of_the_network(
    make_member, account_app, account_settings
):
    """The atlas publishes under the handle, so a member chooses one while the network is off."""
    reader = await make_member(identity=False)
    account_app.state.settings = account_settings.model_copy(
        update={"feature_social": False, "feature_atlas": True}
    )

    chosen = await reader.http.put(
        "/me/public-identity", json={"handle": "basira", "public_name": "Basira"}
    )
    assert chosen.status_code == 200, chosen.text
    shown = await reader.http.get("/me/public-identity")
    assert shown.json() == {"handle": "basira", "public_name": "Basira"}
    for method, path in (
        ("GET", "/u/basira"),
        ("PUT", "/u/basira/follow"),
        ("DELETE", "/u/basira/follow"),
        ("GET", "/blocks"),
        ("PUT", "/blocks/basira"),
        ("DELETE", "/blocks/basira"),
    ):
        response = await reader.http.request(method, path)
        assert response.status_code == 404, path

    account_app.state.settings = account_settings.model_copy(
        update={"feature_social": False, "feature_atlas": False}
    )
    assert (await reader.http.get("/me/public-identity")).status_code == 404
    assert (await reader.http.put("/me/public-identity", json={})).status_code == 404


async def test_the_social_routes_are_never_cached_because_they_carry_the_viewers_own_state(
    make_member,
):
    reader = await make_member("reader")

    for path in (
        "/u/reader",
        "/feed/latest",
        "/feed/for-you",
        "/me/bookmarks",
        "/blocks",
        "/me/public-identity",
    ):
        response = await reader.http.get(path)
        assert response.headers["cache-control"] == "no-store", path
