"""Decision 64: the real full name is public only while its own consent is given."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.features import FeatureFlag
from src.models import Consent, User
from src.models.consent import ConsentKind
from tests.conftest import PASSPHRASE
from tests.helpers import switched
from tests.test_auth_email_routes import request_reset
from tests.test_auth_routes import LOGIN, SIGNUP
from tests.test_google_routes import begin, finish, google  # noqa: F401  (the `google` fixture)

VERSIONS = {
    "terms_version": SIGNUP["accepted_terms_version"],
    "privacy_version": SIGNUP["accepted_privacy_version"],
}


@pytest.fixture
def account_settings(account_settings):
    """The comment of the handle-alone test below needs comments, which are off by default."""
    return switched(account_settings, on=[FeatureFlag.SOCIAL_COMMENTS])


async def name_rows(db):
    return (
        await db.execute(
            select(Consent.version, Consent.granted)
            .where(Consent.kind == ConsentKind.PUBLIC_FULL_NAME)
            .order_by(Consent.created_at, Consent.id)
        )
    ).all()


async def test_signing_up_without_the_box_records_no_consent_and_shows_no_name(
    web, db_session, mailbox
):
    response = await web.post("/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    assert response.json()["public_full_name"] is False
    # An unticked box is a recorded refusal (decision 64).
    assert await name_rows(db_session) == [(SIGNUP["accepted_privacy_version"], False)]


async def test_the_ticked_box_is_a_consent_row_mirrored_on_the_account(web, db_session, mailbox):
    response = await web.post("/auth/signup", json={**SIGNUP, "public_full_name": True})

    assert response.json()["public_full_name"] is True
    assert await name_rows(db_session) == [(SIGNUP["accepted_privacy_version"], True)]
    user = await db_session.scalar(select(User).where(User.email == SIGNUP["email"]))
    assert user.public_full_name is True


async def test_an_account_gives_its_real_name_and_the_choice_with_the_acceptance(
    web, make_user, db_session
):
    # What a Google account does after sign-up: it holds Google's name and has accepted nothing.
    await make_user(accepted=False, display_name="Google Name")
    await web.post("/auth/login", json=LOGIN)

    response = await web.post(
        "/auth/legal/accept",
        json={**VERSIONS, "display_name": "  ليلى   أحمد ", "public_full_name": True},
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["display_name"], body["public_full_name"]) == ("ليلى أحمد", True)
    assert await name_rows(db_session) == [(VERSIONS["privacy_version"], True)]


async def test_accepting_again_without_the_name_fields_leaves_both_as_they_are(
    web, make_user, db_session
):
    await make_user(accepted=False, display_name="Kept", public_full_name=True)
    await web.post("/auth/login", json=LOGIN)

    body = (await web.post("/auth/legal/accept", json=VERSIONS)).json()

    assert (body["display_name"], body["public_full_name"]) == ("Kept", True)
    assert await name_rows(db_session) == []


async def test_a_name_that_is_empty_or_holds_control_characters_is_refused(web, make_user):
    await make_user(accepted=False)
    await web.post("/auth/login", json=LOGIN)

    for name in ("   ", "a\u0007b"):
        response = await web.post("/auth/legal/accept", json={**VERSIONS, "display_name": name})
        assert response.status_code == 422


async def test_the_consent_is_given_and_withdrawn_from_the_profile_and_the_history_is_kept(
    web, make_user, db_session
):
    await make_user(verified=True, handle="reader", display_name="Real Person")
    await web.post("/auth/login", json=LOGIN)
    body = {"kind": "public_full_name", "version": "v1"}

    assert (await web.post("/consents", json={**body, "granted": True})).status_code == 201
    assert (await web.get("/auth/me")).json()["public_full_name"] is True
    assert (await web.post("/consents", json={**body, "granted": False})).status_code == 201

    assert (await web.get("/auth/me")).json()["public_full_name"] is False
    assert await name_rows(db_session) == [("v1", True), ("v1", False)]


async def test_a_member_without_the_consent_is_the_handle_alone_everywhere(
    make_member, make_insight, guard
):
    from tests.support_social import publish_post

    author = await make_member("author", display_name="Real Person", public_full_name=False)
    reader = await make_member("reader")
    guest = await make_member(signed_in=False)
    post_id = await publish_post(author, make_insight)
    commented = await author.http.post(f"/posts/{post_id}/comments", json={"body": "تعليق"})
    await reader.http.put("/blocks/author")

    post = await guest.http.get(f"/posts/{post_id}")
    thread = await guest.http.get(f"/posts/{post_id}/comments")
    blocks = await reader.http.get("/blocks")

    assert post.json()["author"] == {"handle": "author", "public_name": None, "country": None}
    assert commented.json()["author"] == {"handle": "author", "public_name": None}
    assert thread.json()["items"][0]["author"] == {"handle": "author", "public_name": None}
    assert blocks.json() == [{"handle": "author", "public_name": None}]
    for response in (post, thread, blocks):
        assert "Real Person" not in response.text


# ─── Under 13, withdrawal, takeover, names ────────────────────────────────────


async def test_an_account_under_13_cannot_consent_and_declaring_it_withdraws_the_consent(
    web, make_user, db_session
):
    await make_user(public_full_name=True)
    await web.post("/auth/login", json=LOGIN)

    declared = await web.patch("/profile", json={"age_range": "under_13"})
    refused = await web.post(
        "/consents", json={"kind": "public_full_name", "version": "v1", "granted": True}
    )

    assert declared.status_code == 200
    assert (await web.get("/auth/me")).json()["public_full_name"] is False
    assert (refused.status_code, refused.json()["error"]) == (403, "CONSENT_NOT_ALLOWED")
    assert [granted for _, granted in await name_rows(db_session)] == [False]
    # Declaring it again, with nothing shown, records nothing more.
    await web.patch("/profile", json={"age_range": "under_13"})
    assert len(await name_rows(db_session)) == 1


async def test_withdrawing_a_consent_needs_no_acceptance_but_giving_one_does(web, make_user):
    await make_user(accepted=False, public_full_name=True)
    await web.post("/auth/login", json=LOGIN)
    body = {"kind": "public_full_name", "version": "v1"}

    giving = await web.post("/consents", json={**body, "granted": True})
    withdrawing = await web.post("/consents", json={**body, "granted": False})

    assert (giving.status_code, giving.json()["error"]) == (403, "legal_acceptance_required")
    assert withdrawing.status_code == 201
    assert (await web.get("/auth/me")).json()["public_full_name"] is False


async def test_google_taking_over_an_unproved_account_withdraws_the_strangers_name_and_consent(
    web,
    db_session,
    google,  # noqa: F811
    make_user,
):
    await make_user(verified=False, display_name="Stranger Name", public_full_name=True)
    state, nonce, _ = await begin(web)

    await finish(web, google, state, nonce, name="Owner Name")

    me = (await web.get("/auth/me")).json()
    assert (me["display_name"], me["public_full_name"]) == ("Owner Name", False)
    assert [granted for _, granted in await name_rows(db_session)] == [False]


async def test_a_password_reset_of_an_unproved_account_clears_the_name_and_asks_again(
    web, db_session, make_user, mailbox
):
    await make_user(verified=False, display_name="Stranger Name", public_full_name=True)
    _, token = await request_reset(web, mailbox)

    reset = await web.post("/auth/reset-password", json={"token": token, "password": PASSPHRASE})
    await web.post("/auth/login", json=LOGIN)

    assert reset.status_code == 200
    me = (await web.get("/auth/me")).json()
    assert (me["display_name"], me["public_full_name"]) == ("", False)
    assert me["legal_acceptance_required"] is True
    assert [granted for _, granted in await name_rows(db_session)] == [False]


async def test_a_reset_of_a_verified_account_keeps_the_name_and_the_consent(
    web, make_user, mailbox
):
    await make_user(verified=True, display_name="Owner", public_full_name=True)
    _, token = await request_reset(web, mailbox)

    await web.post("/auth/reset-password", json={"token": token, "password": PASSPHRASE})
    await web.post("/auth/login", json=LOGIN)

    me = (await web.get("/auth/me")).json()
    assert (me["display_name"], me["public_full_name"]) == ("Owner", True)


async def test_a_google_name_that_fails_the_checks_is_empty_and_never_the_address(
    web,
    google,  # noqa: F811
):
    for name in ("see https://x.example", "a@b.co", "<b>x</b>", None):
        state, nonce, _ = await begin(web)
        await finish(
            web,
            google,
            state,
            nonce,
            name=name,
            sub=f"sub-{name}",
            email=f"{abs(hash(name))}@example.com",
        )
        assert (await web.get("/auth/me")).json()["display_name"] == ""


async def test_an_account_without_a_name_must_give_one_to_accept(web, make_user):
    await make_user(accepted=False, display_name="")
    await web.post("/auth/login", json=LOGIN)

    refused = await web.post("/auth/legal/accept", json=VERSIONS)
    given = await web.post("/auth/legal/accept", json={**VERSIONS, "display_name": "ليلى أحمد"})

    assert refused.status_code == 422
    assert given.json()["display_name"] == "ليلى أحمد"


async def test_a_name_is_taken_only_while_the_acceptance_is_pending(web, make_user):
    await make_user(display_name="Kept")
    await web.post("/auth/login", json=LOGIN)

    renamed = await web.post("/auth/legal/accept", json={**VERSIONS, "display_name": "Changed"})

    assert (renamed.status_code, renamed.json()["error"]) == (409, "CONFLICT")
    assert (await web.get("/auth/me")).json()["display_name"] == "Kept"


async def test_a_name_with_an_address_or_a_link_is_refused_at_every_write(web, make_user):
    await make_user(accepted=False)
    await web.post("/auth/login", json=LOGIN)

    for name in ("a@b.co", "see https://x.example", "www.x.example", "<b>x</b>"):
        refused = await web.post("/auth/legal/accept", json={**VERSIONS, "display_name": name})
        assert refused.status_code == 422, name
        assert (
            await web.post("/auth/signup", json={**SIGNUP, "display_name": name})
        ).status_code == 422
