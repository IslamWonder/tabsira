"""Acceptance never travels through a GET: Google sign-in records none, the server asks for it."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from src.models import Consent, User
from src.models.consent import ConsentKind
from tests.test_google_routes import finish, google  # noqa: F401  (the `google` fixture)


async def begin_with(web, **params):
    response = await web.get("/auth/google/start", params=params)
    assert response.status_code == 302
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    return query["state"], query["nonce"]


async def consent_rows(db):
    return (await db.execute(select(Consent.kind, Consent.version, Consent.granted))).all()


async def test_a_new_google_account_has_no_acceptance_even_when_the_link_claims_one(
    web,
    db_session,
    google,  # noqa: F811
):
    # A link someone else crafted must not accept the terms for the person who follows it.
    state, nonce = await begin_with(web, terms="2026-10-04", privacy="2026-10-04")

    await finish(web, google, state, nonce)

    assert await consent_rows(db_session) == []
    assert (await web.get("/auth/me")).json()["legal_acceptance_required"] is True


async def test_a_takeover_withdraws_the_strangers_acceptance_so_the_owner_is_asked(
    web,
    db_session,
    google,  # noqa: F811
    make_user,
):
    stranger = await make_user(verified=False)
    for kind in (ConsentKind.TERMS, ConsentKind.PRIVACY):
        db_session.add(Consent(user_id=stranger.id, kind=kind, version="2026-10-04", granted=True))
    await db_session.flush()
    state, nonce = await begin_with(web)

    await finish(web, google, state, nonce)

    assert (await web.get("/auth/me")).json()["legal_acceptance_required"] is True
    withdrawn = await db_session.scalars(select(Consent).where(Consent.granted.is_(False)))
    assert {row.kind for row in withdrawn} == {ConsentKind.TERMS, ConsentKind.PRIVACY}


async def test_an_existing_account_signing_in_gets_no_rows(
    web,
    db_session,
    google,  # noqa: F811
    make_user,
):
    user = await make_user(email="reader@example.com", password=None, verified=True)
    state, nonce = await begin_with(web)

    await finish(web, google, state, nonce)

    assert await consent_rows(db_session) == []
    assert (await db_session.scalars(select(User.id))).one() == user.id
