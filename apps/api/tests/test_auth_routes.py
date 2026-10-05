from __future__ import annotations

import logging

import bcrypt
import pytest
from sqlalchemy import func, select

from src.models import Consent, LoginAttempt, Session, User
from src.models.consent import ConsentKind
from src.services import auth_service, session_service
from tests.conftest import BROWSER_ORIGIN, PASSPHRASE

SIGNUP = {
    "email": "reader@example.com",
    "password": PASSPHRASE,
    "display_name": "ليلى",
    "accepted_terms_version": "2026-10-05T18:00Z",
    "accepted_privacy_version": "2026-10-05T23:30Z",
}
LOGIN = {"email": "reader@example.com", "password": PASSPHRASE}


async def sessions_of(db, email="reader@example.com"):
    return (
        await db.scalars(
            select(Session).join(User, User.id == Session.user_id).where(User.email == email)
        )
    ).all()


# ─── Sign up ──────────────────────────────────────────────────────────────────


async def test_signing_up_creates_the_account_signs_it_in_and_answers_with_it(
    web, db_session, mailbox
):
    response = await web.post("/auth/signup", json=SIGNUP)

    body = response.json()
    assert response.status_code == 201
    assert body["email"] == "reader@example.com"
    assert body["display_name"] == "ليلى"
    assert (body["is_admin"], body["email_verified"], body["has_password"]) == (False, False, True)
    assert body["providers"] == []
    assert set(body) == {
        "id",
        "email",
        "display_name",
        "is_admin",
        "email_verified",
        "has_password",
        "providers",
        "created_at",
        "legal_acceptance_required",
        "profile_completed",
        "public_full_name",
        "has_own_insight",
    }
    assert (body["profile_completed"], body["public_full_name"]) == (False, False)
    assert body["has_own_insight"] is False
    assert PASSPHRASE not in response.text
    assert response.headers["cache-control"] == "no-store"
    me = await web.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]


async def test_the_session_cookie_is_http_only_secure_lax_and_on_the_shared_domain(web):
    response = await web.post("/auth/signup", json=SIGNUP)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Secure-tabsira_session=")
    assert {"HttpOnly", "Secure", "SameSite=lax", "Domain=.tabsira.test", "Path=/"} <= {
        part.strip() for part in cookie.split(";")
    }
    assert "Max-Age=2592000" in cookie


async def test_the_password_is_stored_as_a_bcrypt_hash_and_the_address_lower_cased(web, db_session):
    await web.post("/auth/signup", json={**SIGNUP, "email": "Reader@Example.COM"})

    user = await db_session.scalar(select(User))
    assert user.email == "reader@example.com"
    assert user.password_hash.startswith("$2b$")
    assert bcrypt.checkpw(PASSPHRASE.encode(), user.password_hash.encode())
    assert PASSPHRASE not in user.password_hash


async def test_the_session_holds_only_the_hash_of_the_cookie_and_a_keyed_hash_of_the_ip(
    web, db_session
):
    response = await web.post("/auth/signup", json=SIGNUP, headers={"User-Agent": "TestAgent/1"})

    token = response.cookies["__Secure-tabsira_session"]
    (session,) = await sessions_of(db_session)
    assert session.token_hash != token.encode()
    assert token.encode() not in session.token_hash
    assert session.user_agent == "TestAgent/1"
    assert len(session.ip_hash) == 64
    assert "127.0.0.1" not in session.ip_hash


async def test_signing_up_also_creates_the_empty_profile(web):
    await web.post("/auth/signup", json=SIGNUP)

    profile = await web.get("/profile")

    assert profile.json()["age_range"] == "unknown"


async def test_signing_up_mails_a_verification_link_that_verifies(web, mailbox):
    await web.post("/auth/signup", json=SIGNUP)

    (message,) = mailbox
    text = message.get_body(preferencelist=("plain",)).get_content()
    token = text.split("#token=")[1].split()[0]
    assert message["To"] == "reader@example.com"
    assert "/verify-email#token=" in text
    assert (await web.get("/auth/me")).json()["email_verified"] is False

    verified = await web.post("/auth/verify-email", json={"token": token})

    assert verified.status_code == 200
    assert (await web.get("/auth/me")).json()["email_verified"] is True


async def test_a_mail_that_cannot_be_sent_does_not_fail_the_sign_up(web, monkeypatch, caplog):
    from src.services import email_service

    def fail(_settings, _message):
        message = "smtp down"
        raise OSError(message)

    monkeypatch.setattr(email_service, "deliver", fail)

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        response = await web.post("/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    assert "Failed to send email verification" in caplog.text


async def test_without_smtp_the_sign_up_still_works_and_the_api_logs_an_error(
    make_settings, db_session, caplog
):
    from src.database import get_db
    from src.main import create_app
    from tests.conftest import browser_for

    application = create_app(make_settings(password_bcrypt_rounds=4, smtp_host=""))

    async def use_session():
        yield db_session

    application.dependency_overrides[get_db] = use_session

    with caplog.at_level(logging.ERROR, logger="tabsira.email"):
        async with browser_for(application) as client:
            response = await client.post("/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    assert "SMTP is not configured" in caplog.text


async def test_an_address_in_use_is_a_409_whatever_its_case(web):
    await web.post("/auth/signup", json=SIGNUP)

    again = await web.post("/auth/signup", json={**SIGNUP, "email": "READER@example.com"})

    assert again.status_code == 409
    assert again.json()["error"] == "EMAIL_TAKEN"


async def test_two_sign_ups_racing_for_one_address_leave_one_account_and_a_409(
    web, db_session, make_user, monkeypatch
):
    await make_user("reader@example.com")

    async def not_yet_visible(_db, _email):
        return None

    # The second request's existence check ran before the first one committed.
    monkeypatch.setattr(auth_service, "find_by_email", not_yet_visible)

    response = await web.post("/auth/signup", json=SIGNUP)

    assert response.status_code == 409
    assert response.json()["error"] == "EMAIL_TAKEN"
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    # The failed attempt was recorded.
    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 1


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"email": "not-an-email"}, "email"),
        ({"email": ""}, "email"),
        ({"password": "short"}, "password"),
        ({"password": "x" * 73}, "password"),
        ({"password": "has a null\x00 inside"}, "password"),
        ({"display_name": ""}, "display_name"),
        ({"display_name": "   "}, "display_name"),
        ({"display_name": "bell\x07"}, "display_name"),
        ({"display_name": "bidi" + chr(0x202E) + "override"}, "display_name"),
        ({"display_name": "x" * 61}, "display_name"),
        ({"display_name": "x" * 121}, "display_name"),
    ],
)
async def test_a_bad_sign_up_is_a_422_that_never_echoes_the_password(
    web, db_session, changes, field
):
    response = await web.post("/auth/signup", json={**SIGNUP, **changes})

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert [f["loc"] for f in response.json()["fields"]] == [["body", field]]
    assert PASSPHRASE not in response.text
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0


async def test_unknown_fields_are_refused_so_nobody_can_send_is_admin(web, db_session):
    response = await web.post("/auth/signup", json={**SIGNUP, "is_admin": True})

    assert response.status_code == 422


async def test_the_display_name_is_trimmed_and_its_spaces_and_line_breaks_collapsed(web):
    response = await web.post("/auth/signup", json={**SIGNUP, "display_name": "  ليلى  \n أحمد "})

    assert response.json()["display_name"] == "ليلى أحمد"


async def test_sign_ups_are_rate_limited_per_ip_before_any_password_is_hashed(
    web, db_session, monkeypatch
):
    statuses = []
    for number in range(22):
        response = await web.post(
            "/auth/signup", json={**SIGNUP, "email": f"reader{number}@example.com"}
        )
        statuses.append(response.status_code)

    assert statuses[:20] == [201] * 20
    assert statuses[20:] == [429, 429]
    limited = response
    assert limited.json()["error"] == "RATE_LIMITED"
    assert limited.headers["retry-after"] == "900"


async def test_sign_ups_are_rate_limited_per_email(web):
    statuses = [(await web.post("/auth/signup", json=SIGNUP)).status_code for _ in range(6)]

    # One 201, then 409s that count too, until the address is limited.
    assert statuses == [201, 409, 409, 409, 409, 429]


# ─── Sign up: the terms and the privacy policy ───────────────────────────────


async def consents_of(db, email="reader@example.com"):
    return (
        await db.execute(
            select(Consent.kind, Consent.version, Consent.granted)
            .join(User, User.id == Consent.user_id)
            .where(User.email == email)
        )
    ).all()


async def test_signing_up_records_the_acceptance_of_both_texts(web, db_session):
    response = await web.post("/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    rows = await consents_of(db_session)
    assert {(row.kind, row.version, row.granted) for row in rows} == {
        (ConsentKind.TERMS, "2026-10-05T18:00Z", True),
        (ConsentKind.PRIVACY, "2026-10-05T23:30Z", True),
        # The unticked full-name box is a recorded refusal.
        (ConsentKind.PUBLIC_FULL_NAME, "2026-10-05T23:30Z", False),
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"accepted_terms_version": "2020-01-01"},
        {"accepted_privacy_version": "2020-01-01"},
        {"accepted_terms_version": "2026-10-05T18:00Z "},
    ],
)
async def test_an_old_or_wrong_version_is_refused_before_anything_is_created(
    web, db_session, changes
):
    response = await web.post("/auth/signup", json={**SIGNUP, **changes})

    assert response.status_code == 422
    assert response.json()["error"] == "legal_acceptance_required"
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Consent)) == 0
    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 0


@pytest.mark.parametrize("missing", ["accepted_terms_version", "accepted_privacy_version"])
async def test_a_sign_up_that_does_not_name_both_versions_is_a_validation_error(web, missing):
    body = {key: value for key, value in SIGNUP.items() if key != missing}

    response = await web.post("/auth/signup", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert [f["loc"] for f in response.json()["fields"]] == [["body", missing]]


# ─── Sign in ──────────────────────────────────────────────────────────────────


async def test_signing_in_starts_a_session(web, make_user):
    await make_user()

    response = await web.post("/auth/login", json=LOGIN)

    assert response.status_code == 200
    assert response.json()["email"] == "reader@example.com"
    assert "set-cookie" in response.headers
    assert (await web.get("/auth/me")).status_code == 200


async def test_the_address_is_matched_whatever_its_case_or_padding(web, make_user):
    await make_user("reader@example.com")

    response = await web.post("/auth/login", json={**LOGIN, "email": "Reader@Example.com"})

    assert response.status_code == 200


async def test_a_wrong_password_and_an_unknown_address_get_the_same_answer(web, make_user):
    await make_user()

    wrong = await web.post("/auth/login", json={**LOGIN, "password": "not the password"})
    unknown = await web.post("/auth/login", json={**LOGIN, "email": "nobody@example.com"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in wrong.headers


async def test_a_google_only_account_cannot_sign_in_with_a_password_and_nobody_can_tell(
    web, make_user
):
    await make_user("google@example.com", password=None)

    response = await web.post(
        "/auth/login", json={"email": "google@example.com", "password": "anything at all"}
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


async def test_an_unknown_address_still_pays_for_a_password_check(web, monkeypatch):
    calls = []
    real = bcrypt.checkpw
    monkeypatch.setattr(
        bcrypt, "checkpw", lambda password, hashed: calls.append(1) or real(password, hashed)
    )

    await web.post("/auth/login", json={**LOGIN, "email": "nobody@example.com"})

    assert calls == [1]


async def test_a_disabled_account_with_the_right_password_is_told_so(web, make_user):
    await make_user(is_active=False)

    response = await web.post("/auth/login", json=LOGIN)

    assert response.status_code == 403
    assert response.json()["error"] == "ACCOUNT_DISABLED"
    assert "set-cookie" not in response.headers


async def test_a_deleted_account_cannot_sign_in(web, make_user, moving_clock):
    await make_user(deleted_at=moving_clock.now)

    assert (await web.post("/auth/login", json=LOGIN)).status_code == 403


async def test_an_unverified_account_can_sign_in(web, make_user):
    await make_user(verified=False)

    assert (await web.post("/auth/login", json=LOGIN)).json()["email_verified"] is False


async def test_failed_sign_ins_lock_an_address_after_five_and_even_the_right_password_waits(
    web, make_user
):
    await make_user()
    for _ in range(5):
        assert (
            await web.post("/auth/login", json={**LOGIN, "password": "wrong password!"})
        ).status_code == 401

    locked = await web.post("/auth/login", json=LOGIN)

    assert locked.status_code == 429
    assert locked.json()["error"] == "RATE_LIMITED"
    assert locked.headers["retry-after"] == "900"


async def test_the_lock_is_the_same_for_an_address_that_does_not_exist(web):
    statuses = [
        (await web.post("/auth/login", json={**LOGIN, "email": "ghost@example.com"})).status_code
        for _ in range(6)
    ]

    assert statuses == [401] * 5 + [429]


async def test_the_lock_lifts_when_the_window_has_passed(web, make_user, moving_clock):
    await make_user()
    for _ in range(5):
        await web.post("/auth/login", json={**LOGIN, "password": "wrong password!"})
    moving_clock.advance(seconds=901)

    assert (await web.post("/auth/login", json=LOGIN)).status_code == 200


async def test_failed_sign_ins_are_limited_per_ip_across_addresses(web):
    statuses = [
        (
            await web.post("/auth/login", json={**LOGIN, "email": f"ghost{n}@example.com"})
        ).status_code
        for n in range(22)
    ]

    assert statuses == [401] * 20 + [429, 429]


async def test_successful_sign_ins_do_not_lock_anyone(web, make_user):
    await make_user()

    statuses = [(await web.post("/auth/login", json=LOGIN)).status_code for _ in range(8)]

    assert statuses == [200] * 8


async def test_signing_in_again_ends_the_session_the_browser_held(web, make_user, db_session):
    await make_user()
    await web.post("/auth/login", json=LOGIN)
    first = web.cookies["__Secure-tabsira_session"]

    await web.post("/auth/login", json=LOGIN)

    assert web.cookies["__Secure-tabsira_session"] != first
    assert len(await sessions_of(db_session)) == 1


async def test_a_planted_cookie_is_never_the_one_that_ends_up_signed_in(web, make_user, db_session):
    await make_user()
    web.cookies.set("__Secure-tabsira_session", "planted-by-an-attacker", domain=".tabsira.test")

    await web.post("/auth/login", json=LOGIN)

    assert web.cookies["__Secure-tabsira_session"] != "planted-by-an-attacker"


async def test_a_login_with_unknown_fields_or_a_bad_address_is_a_422(web):
    assert (await web.post("/auth/login", json={**LOGIN, "remember": True})).status_code == 422
    assert (await web.post("/auth/login", json={**LOGIN, "email": "nope"})).status_code == 422
    assert (await web.post("/auth/login", json={**LOGIN, "password": ""})).status_code == 422


# ─── Sign out, who am I, providers ────────────────────────────────────────────


async def test_signing_out_ends_the_session_and_clears_the_cookie(web, make_user, db_session):
    await make_user()
    await web.post("/auth/login", json=LOGIN)
    stolen = web.cookies["__Secure-tabsira_session"]

    response = await web.post("/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert await sessions_of(db_session) == []
    # The cookie value is worthless now, even if somebody kept a copy.
    web.cookies.set("__Secure-tabsira_session", stolen, domain=".tabsira.test")
    assert (await web.get("/auth/me")).status_code == 401


async def test_signing_out_twice_or_without_a_session_is_the_same_204(web):
    assert (await web.post("/auth/logout")).status_code == 204
    assert (await web.post("/auth/logout")).status_code == 204


async def test_who_am_i_needs_a_session(web):
    response = await web.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"error": "UNAUTHORIZED", "detail": "Sign in first."}


async def test_a_session_that_expired_is_signed_out(web, make_user, moving_clock):
    await make_user()
    await web.post("/auth/login", json=LOGIN)
    moving_clock.advance(days=31)

    assert (await web.get("/auth/me")).status_code == 401


async def test_who_am_i_lists_the_linked_providers_and_never_the_private_profile(
    web, make_user, db_session
):
    from src.models import OAuthAccount

    user = await make_user(password=None, verified=True)
    db_session.add(OAuthAccount(user_id=user.id, provider="google", subject="s"))
    await db_session.flush()
    session = await session_service.create(
        db_session,
        web._transport.app.state.settings,
        user_id=user.id,
        ip_hash="ip",
        user_agent=None,
    )
    web.cookies.set("__Secure-tabsira_session", session, domain=".tabsira.test")
    await web.patch(
        "/profile", json={"religious_background": "muslim", "gender": "woman", "age_range": "25_39"}
    )

    response = await web.get("/auth/me")

    body = response.json()
    assert (body["providers"], body["has_password"], body["email_verified"]) == (
        ["google"],
        False,
        True,
    )
    for private in ("muslim", "woman", "25_39", "religious_background", "gender", "age_range"):
        assert private not in response.text


async def test_using_a_session_records_when_it_was_last_seen_at_most_every_five_minutes(
    web, make_user, db_session, moving_clock
):
    await make_user()
    await web.post("/auth/login", json=LOGIN)
    (session,) = await sessions_of(db_session)
    opened = session.last_seen_at

    moving_clock.advance(minutes=2)
    await web.get("/auth/me")
    await db_session.refresh(session)
    assert session.last_seen_at == opened

    moving_clock.advance(minutes=4)
    await web.get("/auth/me")
    await db_session.refresh(session)
    assert session.last_seen_at == moving_clock.now


async def test_a_disabled_account_loses_its_session_at_once(web, make_user, db_session):
    user = await make_user()
    await web.post("/auth/login", json=LOGIN)
    user.is_active = False
    await db_session.flush()

    assert (await web.get("/auth/me")).status_code == 401


async def test_providers_say_whether_google_is_available(web, account_app, make_settings):
    from src.main import create_app
    from tests.conftest import browser_for

    assert (await web.get("/auth/providers")).json() == {
        "providers": [
            {"id": "password", "available": True},
            {"id": "google", "available": True},
        ]
    }
    async with browser_for(create_app(make_settings())) as without_google:
        assert (await without_google.get("/auth/providers")).json()["providers"][1] == {
            "id": "google",
            "available": False,
        }


async def test_the_hashes_in_the_attempt_log_are_keyed_and_hide_the_address(web, db_session):
    await web.post("/auth/login", json={**LOGIN, "email": "ghost@example.com"})

    attempt = await db_session.scalar(select(LoginAttempt))

    assert attempt.email_hash == auth_service.hash_email(
        web._transport.app.state.settings, "GHOST@example.com"
    )
    assert "ghost" not in attempt.email_hash
    assert "127.0.0.1" not in attempt.ip_hash


# ─── The browser's origin ─────────────────────────────────────────────────────


async def test_a_state_changing_request_from_another_origin_is_refused(web):
    response = await web.post(
        "/auth/signup", json=SIGNUP, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "ORIGIN_NOT_ALLOWED"
    assert "x-request-id" in response.headers


async def test_the_api_may_post_to_itself_and_the_web_origin_may_post(web):
    own = await web.post("/auth/logout", headers={"Origin": "https://api.tabsira.test"})
    web_origin = await web.post("/auth/logout", headers={"Origin": BROWSER_ORIGIN})

    assert own.status_code == web_origin.status_code == 204


async def test_the_attempt_is_counted_before_the_password_is_checked(
    web, make_user, db_session, monkeypatch
):
    from sqlalchemy import func, select

    from src.models import LoginAttempt
    from src.services import auth_service

    await make_user()
    original = auth_service.find_by_email
    counted = []

    async def spy(*args, **kwargs):
        # Everything after this includes the slow password check; parallel requests all pass
        # a count made before it, so the attempt must already be on record here.
        counted.append(await db_session.scalar(select(func.count()).select_from(LoginAttempt)))
        return await original(*args, **kwargs)

    monkeypatch.setattr(auth_service, "find_by_email", spy)

    await web.post("/auth/login", json=LOGIN)

    assert counted == [1]


async def test_the_sign_up_attempt_is_counted_before_the_password_is_hashed(
    web, db_session, monkeypatch
):
    from sqlalchemy import func, select

    from src.models import LoginAttempt
    from src.services import auth_service

    original = auth_service.find_by_email
    counted = []

    async def spy(*args, **kwargs):
        # Everything after this includes the slow hash; parallel sign-ups all pass a count made
        # before it, so the attempt must already be on record here.
        counted.append(await db_session.scalar(select(func.count()).select_from(LoginAttempt)))
        return await original(*args, **kwargs)

    monkeypatch.setattr(auth_service, "find_by_email", spy)

    response = await web.post("/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    assert counted == [1]


async def test_a_refused_sign_up_counts_once(web, db_session):
    from sqlalchemy import func, select

    from src.models import LoginAttempt

    await web.post("/auth/signup", json=SIGNUP)
    again = await web.post("/auth/signup", json=SIGNUP)

    assert again.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(LoginAttempt)) == 2
