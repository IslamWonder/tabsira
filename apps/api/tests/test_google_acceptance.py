"""Google sign-up accepts the terms and the privacy policy; a returning account is untouched."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from src.models import Consent, OAuthState, User
from src.models.consent import ConsentKind
from tests.test_google_routes import finish, google  # noqa: F401  (the `google` fixture)

CURRENT = {"terms": "2026-10-04", "privacy": "2026-10-04"}


async def begin_with(web, **params):
    response = await web.get("/auth/google/start", params=params)
    assert response.status_code == 302
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    return query["state"], query["nonce"]


async def accepted(db):
    rows = (await db.execute(select(Consent.kind, Consent.version, Consent.granted))).all()
    return {(row.kind.value, row.version, row.granted) for row in rows}


async def test_the_versions_are_kept_with_the_state_until_the_callback(web, db_session, google):  # noqa: F811
    await begin_with(web, **CURRENT)

    row = (await db_session.scalars(select(OAuthState))).one()

    assert (row.accepted_terms_version, row.accepted_privacy_version) == ("2026-10-04",) * 2


async def test_a_new_account_records_both_rows_when_both_versions_are_current(
    web,
    db_session,
    google,  # noqa: F811
):
    state, nonce = await begin_with(web, **CURRENT)

    await finish(web, google, state, nonce)

    assert await accepted(db_session) == {
        ("terms", "2026-10-04", True),
        ("privacy", "2026-10-04", True),
    }
    assert (await web.get("/auth/me")).json()["legal_acceptance_required"] is False


async def test_a_new_account_without_current_versions_records_nothing_and_is_asked(
    web,
    db_session,
    google,  # noqa: F811
):
    state, nonce = await begin_with(web, terms="2026-10-04", privacy="2020-01-01")

    await finish(web, google, state, nonce)

    assert await accepted(db_session) == set()
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


async def test_an_existing_account_signing_in_is_unaffected(
    web,
    db_session,
    google,  # noqa: F811
    make_user,
):
    user = await make_user(email="reader@example.com", password=None, verified=True)
    state, nonce = await begin_with(web, **CURRENT)

    await finish(web, google, state, nonce)

    assert await accepted(db_session) == set()
    assert (await db_session.scalars(select(User.id))).one() == user.id
