"""Decision 63: the real full name is public only while its own consent is given."""

from __future__ import annotations

from sqlalchemy import select

from src.models import Consent, User
from src.models.consent import ConsentKind
from tests.test_auth_routes import LOGIN, SIGNUP

VERSIONS = {
    "terms_version": SIGNUP["accepted_terms_version"],
    "privacy_version": SIGNUP["accepted_privacy_version"],
}


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
    assert await name_rows(db_session) == []


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

    assert post.json()["author"] == {"handle": "author", "public_name": None}
    assert commented.json()["author"] == {"handle": "author", "public_name": None}
    assert thread.json()["items"][0]["author"] == {"handle": "author", "public_name": None}
    assert blocks.json() == [{"handle": "author", "public_name": None}]
    for response in (post, thread, blocks):
        assert "Real Person" not in response.text
