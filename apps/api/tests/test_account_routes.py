from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select, text

from src.models import (
    Consent,
    CookieConsent,
    EmailToken,
    OAuthAccount,
    Profile,
    Session,
    TokenPurpose,
    User,
)
from tests.conftest import PASSPHRASE, browser_for

LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}


@pytest.fixture
async def reader(web, make_user):
    user = await make_user(verified=True)
    await web.post("/auth/login", json=LOGIN)
    return user


async def count(db, model):
    return await db.scalar(select(func.count()).select_from(model))


# ─── Export ───────────────────────────────────────────────────────────────────


async def test_the_export_needs_a_session(web):
    assert (await web.get("/account/export")).status_code == 401


async def test_the_export_holds_everything_the_account_owns_as_a_download(web, reader, db_session):
    db_session.add(OAuthAccount(user_id=reader.id, provider="google", subject="sub-1"))
    await db_session.flush()
    await web.patch(
        "/profile", json={"goals": ["curiosity"], "age_range": "18_24", "gender": "woman"}
    )
    await web.post("/consents", json={"kind": "photo_storage", "version": "v1", "granted": True})
    await web.post("/consents", json={"kind": "photo_storage", "version": "v2", "granted": False})

    response = await web.get("/account/export")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="tabsira-export.json"'
    assert response.headers["cache-control"] == "no-store"
    assert set(body) == {
        "exported_at",
        "user",
        "oauth_accounts",
        "sessions",
        "profile",
        "consents",
        "cookie_consents",
        "social",
        "map_entries",
        "sponsorships",
        "learning",
    }
    assert body["user"]["email"] == "reader@example.com"
    assert body["user"]["id"] == str(reader.id)
    assert [(a["provider"], a["subject"]) for a in body["oauth_accounts"]] == [("google", "sub-1")]
    assert len(body["sessions"]) == 1
    assert body["profile"]["goals"] == ["curiosity"]
    assert (body["profile"]["age_range"], body["profile"]["gender"]) == ("18_24", "woman")
    photo = [c for c in body["consents"] if c["kind"] == "photo_storage"]
    assert [(c["version"], c["granted"]) for c in photo] == [("v1", True), ("v2", False)]


async def test_the_export_leaves_out_every_credential(web, reader, db_session):
    response = await web.get("/account/export")

    text_ = response.text
    session = await db_session.scalar(select(Session))
    assert "password" not in text_
    assert "token_hash" not in text_
    assert session.token_hash.hex() not in text_
    assert web.cookies["__Secure-tabsira_session"] not in text_
    user = await db_session.scalar(select(User))
    assert user.password_hash not in text_
    assert set(response.json()["sessions"][0]) == {
        "created_at",
        "expires_at",
        "last_seen_at",
        "ip_hash",
        "user_agent",
    }


async def test_the_export_is_only_about_the_caller(web, reader, make_user, account_app):
    other = await make_user("other@example.com")
    await web.patch("/profile", json={"gender": "man"})
    async with browser_for(account_app) as theirs:
        await theirs.post(
            "/auth/login", json={"email": "other@example.com", "password": PASSPHRASE}
        )

        body = (await theirs.get("/account/export")).json()

    assert body["user"]["id"] == str(other.id)
    assert body["profile"]["gender"] == "unknown"
    assert "reader@example.com" not in json.dumps(body)


async def test_the_export_shows_the_cookie_choices_made_while_signed_in_and_only_those(
    web, reader, make_user, account_app, db_session
):
    other = await make_user("other@example.com")
    anonymous = browser_for(account_app)
    async with anonymous:
        await anonymous.post("/consent", json={"analytics": True, "behaviour": True})
    first = (await web.post("/consent", json={"analytics": True, "behaviour": False})).json()
    await web.post(
        "/consent",
        json={"consent_id": first["consent_id"], "analytics": False, "behaviour": False},
        headers={"User-Agent": "Mozilla/5.0 Firefox/132.0"},
    )
    db_session.add(
        CookieConsent(
            consent_id=uuid.uuid4(),
            policy_version="v1",
            analytics=True,
            behaviour=True,
            user_agent_family="chrome",
            user_id=other.id,
        )
    )
    await db_session.flush()

    body = (await web.get("/account/export")).json()

    choices = body["cookie_consents"]
    assert [(c["analytics"], c["behaviour"]) for c in choices] == [(True, False), (False, False)]
    assert {c["consent_id"] for c in choices} == {first["consent_id"]}
    assert {c["necessary"] for c in choices} == {True}
    assert [c["user_agent_family"] for c in choices] == ["other", "firefox"]
    assert set(choices[0]) == {
        "consent_id",
        "policy_version",
        "necessary",
        "analytics",
        "behaviour",
        "user_agent_family",
        "created_at",
    }


# ─── Deletion ─────────────────────────────────────────────────────────────────


async def test_deleting_the_account_removes_everything_the_user_owns_sessions_included(
    web, reader, db_session, account_app, make_user
):
    from src.services import email_token_service

    survivor = await make_user("survivor@example.com", accepted=False)
    db_session.add(OAuthAccount(user_id=reader.id, provider="google", subject="sub-1"))
    await web.patch("/profile", json={"gender": "woman"})
    await web.post("/consents", json={"kind": "memory", "version": "v1", "granted": True})
    await email_token_service.issue(
        db_session, web._transport.app.state.settings, reader, TokenPurpose.PASSWORD_RESET
    )
    async with browser_for(account_app) as phone:
        await phone.post("/auth/login", json=LOGIN)

        response = await web.delete("/account")

        assert response.status_code == 204
        assert (await phone.get("/auth/me")).status_code == 401
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert await db_session.scalar(select(User).where(User.id == reader.id)) is None
    for model in (OAuthAccount, Consent, EmailToken):
        assert await count(db_session, model) == 0, model
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Session).where(Session.user_id == reader.id)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Profile).where(Profile.user_id == reader.id)
        )
        == 0
    )
    # Somebody else's account is untouched.
    assert await db_session.scalar(select(User).where(User.id == survivor.id)) is not None
    assert await count(db_session, Profile) == 1


async def test_deleting_the_account_removes_its_cookie_choices_and_no_one_elses(
    web, reader, make_user, account_app, db_session
):
    survivor = await make_user("survivor@example.com")
    anonymous = browser_for(account_app)
    async with anonymous:
        await anonymous.post("/consent", json={"analytics": True, "behaviour": True})
    await web.post("/consent", json={"analytics": True, "behaviour": False})
    await web.post("/consent", json={"analytics": False, "behaviour": False})
    db_session.add(
        CookieConsent(
            consent_id=uuid.uuid4(),
            policy_version="v1",
            analytics=True,
            behaviour=True,
            user_agent_family="chrome",
            user_id=survivor.id,
        )
    )
    await db_session.flush()
    assert await count(db_session, CookieConsent) == 4

    assert (await web.delete("/account")).status_code == 204

    left = (await db_session.scalars(select(CookieConsent))).all()
    # The two choices made signed in are gone. The anonymous one and the other account's remain.
    assert sorted(str(row.user_id) for row in left) == sorted([str(survivor.id), "None"])


async def test_after_deletion_the_address_can_be_used_again_and_the_old_login_is_gone(web, reader):
    await web.delete("/account")

    assert (await web.post("/auth/login", json=LOGIN)).status_code == 401
    assert (
        await web.post(
            "/auth/signup",
            json={
                **LOGIN,
                "display_name": "again",
                "accepted_terms_version": "2026-10-05T18:00Z",
                "accepted_privacy_version": "2026-10-05T18:00Z",
            },
        )
    ).status_code == 201


async def test_deleting_twice_or_without_a_session_is_the_same_204(web, reader):
    first = await web.delete("/account")
    second = await web.delete("/account")
    stranger = browser_for(web._transport.app)
    async with stranger:
        third = await stranger.delete("/account")

    assert (first.status_code, second.status_code, third.status_code) == (204, 204, 204)


async def test_a_delete_from_another_origin_is_refused_and_deletes_nothing(web, reader, db_session):
    response = await web.delete("/account", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert await db_session.scalar(select(User).where(User.id == reader.id)) is not None


async def test_deleting_removes_the_rows_even_when_nothing_else_was_ever_stored(
    web, make_user, db_session
):
    await make_user()
    await web.post("/auth/login", json=LOGIN)
    await db_session.execute(text("DELETE FROM app.profiles"))

    assert (await web.delete("/account")).status_code == 204
    assert await count(db_session, User) == 0
