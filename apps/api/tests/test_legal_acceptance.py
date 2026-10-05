"""Accepting the terms and the privacy policy again after a new version."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from src.models import Consent
from src.models.consent import ConsentKind
from src.services import legal_service
from tests.test_auth_routes import LOGIN, SIGNUP

CURRENT = {"terms_version": "2026-10-05T18:00Z", "privacy_version": "2026-10-05T23:30Z"}


async def test_an_account_with_no_acceptance_is_asked_and_accepting_clears_it(web, make_user):
    await make_user(accepted=False)
    await web.post("/auth/login", json=LOGIN)
    assert (await web.get("/auth/me")).json()["legal_acceptance_required"] is True

    response = await web.post("/auth/legal/accept", json=CURRENT)

    assert response.status_code == 200
    assert response.json()["legal_acceptance_required"] is False
    assert (await web.get("/auth/me")).json()["legal_acceptance_required"] is False


async def test_the_export_lists_the_terms_and_privacy_rows(web):
    await web.post("/auth/signup", json=SIGNUP)

    consents = (await web.get("/account/export")).json()["consents"]

    assert {(c["kind"], c["version"], c["granted"]) for c in consents} == {
        ("terms", "2026-10-05T18:00Z", True),
        ("privacy", "2026-10-05T23:30Z", True),
        ("public_full_name", "2026-10-05T23:30Z", False),
    }


async def test_a_sign_up_is_not_asked_again(web):
    body = (await web.post("/auth/signup", json=SIGNUP)).json()

    assert body["legal_acceptance_required"] is False


@pytest.mark.parametrize("which", ["terms", "privacy"])
async def test_a_new_version_asks_again_for_either_text(
    web, make_user, db_session, make_settings, which
):
    user = await make_user(accepted=False)
    await web.post("/auth/login", json=LOGIN)
    await web.post("/auth/legal/accept", json=CURRENT)
    newer = make_settings(**{f"{which}_version": "2027-01-01"})

    assert await legal_service.acceptance_required(db_session, newer, user.id) is True


async def test_a_withdrawn_acceptance_asks_again(make_user, db_session, account_settings):
    user = await make_user(accepted=False)
    for kind, version in (
        (ConsentKind.TERMS, "2026-10-05T18:00Z"),
        (ConsentKind.PRIVACY, "2026-10-05T23:30Z"),
    ):
        db_session.add(Consent(user_id=user.id, kind=kind, version=version, granted=True))
    await db_session.flush()
    assert await legal_service.acceptance_required(db_session, account_settings, user.id) is False

    db_session.add(
        Consent(user_id=user.id, kind=ConsentKind.TERMS, version="2026-10-05T18:00Z", granted=False)
    )
    await db_session.flush()

    assert await legal_service.acceptance_required(db_session, account_settings, user.id) is True


@pytest.mark.parametrize(
    "body",
    [
        {"terms_version": "old", "privacy_version": "2026-10-05T23:30Z"},
        {"terms_version": "2026-10-05T18:00Z", "privacy_version": "old"},
    ],
)
async def test_accepting_an_old_version_is_refused_and_records_nothing(
    web, make_user, db_session, body
):
    await make_user(accepted=False)
    await web.post("/auth/login", json=LOGIN)

    response = await web.post("/auth/legal/accept", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "legal_acceptance_required"
    assert await db_session.scalar(select(func.count()).select_from(Consent)) == 0


async def test_accepting_needs_a_session_and_an_allowed_origin(web):
    assert (await web.post("/auth/legal/accept", json=CURRENT)).status_code == 401
    forbidden = await web.post(
        "/auth/legal/accept", json=CURRENT, headers={"Origin": "https://evil.example"}
    )
    assert forbidden.status_code == 403
