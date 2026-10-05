"""Decision 67: an optional declared country, public only while its own consent is given."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.features import FeatureFlag
from src.models import Consent
from src.models.consent import ConsentKind
from src.models.profile import AgeRange, Profile
from src.services import geo_service, public_identity
from tests import geo_dataset as world_data
from tests.helpers import switched
from tests.support_social import publish_post
from tests.test_auth_routes import LOGIN

SHOW = {"kind": "public_country", "version": "v1"}
TUNISIA = {"code": "TN", "name": "تونس"}


@pytest.fixture
def account_settings(account_settings):
    """The comment thread below needs comments, which are off by default."""
    return switched(account_settings, on=[FeatureFlag.SOCIAL_COMMENTS])


@pytest.fixture
async def world(db_session):
    await world_data.load_world(db_session)


async def country_rows(db):
    return (
        await db.execute(
            select(Consent.version, Consent.granted)
            .where(Consent.kind == ConsentKind.PUBLIC_COUNTRY)
            .order_by(Consent.created_at, Consent.id)
        )
    ).all()


# ─── Declaring a country ──────────────────────────────────────────────────────


async def test_a_country_is_declared_in_either_case_and_cleared_with_null(web, make_user, world):
    await make_user()
    await web.post("/auth/login", json=LOGIN)

    declared = await web.patch("/profile", json={"country": "tn"})
    kept = await web.patch("/profile", json={"gender": "unknown"})
    cleared = await web.patch("/profile", json={"country": None})

    assert (declared.status_code, declared.json()["country"]) == (200, "TN")
    assert declared.json()["show_country"] is False
    assert kept.json()["country"] == "TN"
    assert (cleared.status_code, cleared.json()["country"]) == (200, None)


@pytest.mark.parametrize("code", ["XX", "TUN", "T1", ""])
async def test_a_code_geonames_does_not_list_is_refused(web, make_user, world, code):
    await make_user()
    await web.post("/auth/login", json=LOGIN)

    response = await web.patch("/profile", json={"country": code})

    assert (response.status_code, response.json()["error"]) == (422, "VALIDATION_ERROR")
    assert (await web.get("/profile")).json()["country"] is None


async def test_without_geodata_no_code_is_accepted(web, make_user):
    await make_user()
    await web.post("/auth/login", json=LOGIN)

    response = await web.patch("/profile", json={"country": "TN"})

    assert response.status_code == 422


async def test_the_labels_are_read_once_and_kept(db_session, world, monkeypatch):
    first = await geo_service.country_labels(db_session)

    async def no_query(*_args, **_kwargs):
        raise AssertionError("asked the database again")

    monkeypatch.setattr(db_session, "execute", no_query)

    assert first["TN"] == "تونس"
    assert await geo_service.country_labels(db_session) is first


async def test_the_consent_is_given_and_withdrawn_and_the_history_is_kept(
    web, make_user, db_session
):
    await make_user()
    await web.post("/auth/login", json=LOGIN)

    assert (await web.post("/consents", json={**SHOW, "granted": True})).status_code == 201
    assert (await web.get("/profile")).json()["show_country"] is True
    assert (await web.post("/consents", json={**SHOW, "granted": False})).status_code == 201

    assert (await web.get("/profile")).json()["show_country"] is False
    assert await country_rows(db_session) == [("v1", True), ("v1", False)]


async def test_an_account_under_13_cannot_show_it_and_declaring_it_withdraws_the_consent(
    web, make_user, db_session
):
    await make_user()
    await web.post("/auth/login", json=LOGIN)
    await web.post("/consents", json={**SHOW, "granted": True})

    declared = await web.patch("/profile", json={"age_range": "under_13"})
    refused = await web.post("/consents", json={**SHOW, "granted": True})

    assert declared.json()["show_country"] is False
    assert (refused.status_code, refused.json()["error"]) == (403, "CONSENT_NOT_ALLOWED")
    assert [granted for _, granted in await country_rows(db_session)] == [True, False]
    # Declaring it again, with nothing shown, records nothing more.
    await web.patch("/profile", json={"age_range": "under_13"})
    assert len(await country_rows(db_session)) == 2


async def test_the_export_carries_both_and_deletion_removes_them(web, make_user, db_session, world):
    user = await make_user()
    await web.post("/auth/login", json=LOGIN)
    await web.patch("/profile", json={"country": "SA"})
    await web.post("/consents", json={**SHOW, "granted": True})

    exported = (await web.get("/account/export")).json()["profile"]
    deleted = await web.delete("/account")

    assert (exported["country"], exported["show_country"]) == ("SA", True)
    assert deleted.status_code == 204
    db_session.expire_all()
    assert await db_session.scalar(select(Profile).where(Profile.user_id == user.id)) is None


# ─── What public answers say ──────────────────────────────────────────────────


async def _declare(member, *, shown: bool) -> None:
    await member.http.patch("/profile", json={"country": "TN"})
    await member.http.post("/consents", json={**SHOW, "granted": shown})


async def _public_answers(author, reader, guest, post_id):
    commented = await author.http.post(f"/posts/{post_id}/comments", json={"body": "تعليق"})
    await reader.http.put("/u/author/follow")
    answers = {
        "profile": await guest.http.get("/u/author"),
        "post": await guest.http.get(f"/posts/{post_id}"),
        "member_posts": await guest.http.get("/u/author/posts"),
        "latest": await guest.http.get("/feed/latest"),
        "following": await reader.http.get("/feed/following"),
        "comment": commented,
        "thread": await guest.http.get(f"/posts/{post_id}/comments"),
    }
    await reader.http.put("/blocks/author")
    answers["blocks"] = await reader.http.get("/blocks")
    return answers


async def test_with_the_switch_off_the_country_is_in_no_public_answer(
    make_member, make_insight, guard, world
):
    author = await make_member("author")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    await _declare(author, shown=False)
    post_id = await publish_post(author, make_insight)

    answers = await _public_answers(author, reader, guest, post_id)

    assert answers["profile"].json()["country"] is None
    assert answers["post"].json()["author"]["country"] is None
    for name, response in answers.items():
        assert "تونس" not in response.text, name
        assert '"TN"' not in response.text, name


async def test_with_the_switch_on_only_the_profile_and_the_post_author_show_it(
    make_member, make_insight, guard, world
):
    author = await make_member("author")
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    await _declare(author, shown=True)
    post_id = await publish_post(author, make_insight)

    answers = await _public_answers(author, reader, guest, post_id)

    assert answers["profile"].json()["country"] == TUNISIA
    assert answers["post"].json()["author"]["country"] == TUNISIA
    assert answers["member_posts"].json()["items"][0]["author"]["country"] == TUNISIA
    assert answers["latest"].json()["items"][0]["author"]["country"] == TUNISIA
    assert answers["following"].json()["items"][0]["author"]["country"] == TUNISIA
    for name in ("comment", "thread", "blocks"):
        assert '"TN"' not in answers[name].text, name
        assert "تونس" not in answers[name].text, name


async def test_an_account_declared_under_13_never_shows_it_whatever_set_the_age(
    db_session, make_member, world
):
    author = await make_member("author")
    await _declare(author, shown=True)
    # A path other than PATCH /profile (an import, an admin fix) leaves the switch on.
    profile = await db_session.scalar(select(Profile).where(Profile.user_id == author.user.id))
    profile.age_range = AgeRange.UNDER_13
    await db_session.flush()

    assert await public_identity.shown_countries(db_session, [author.user.id]) == {}


async def test_a_country_geonames_no_longer_names_is_not_shown(db_session, make_member, world):
    author = await make_member("author")
    await _declare(author, shown=True)
    geo_service.forget_country_labels()
    await geo_service.country_labels(db_session)
    geo_service._country_labels.pop("TN")

    assert await public_identity.shown_countries(db_session, [author.user.id]) == {}
    assert await public_identity.shown_countries(db_session, []) == {}
