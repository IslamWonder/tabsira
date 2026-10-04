"""GET /legal: public, cacheable, the versions and the addresses from the settings."""

from __future__ import annotations

from src.main import create_app
from tests.helpers import client_for


async def test_legal_needs_no_session_and_is_cacheable_for_five_minutes(client):
    response = await client.get("/legal")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.json() == {
        "terms_version": "2026-10-04",
        "privacy_version": "2026-10-04",
        "privacy_email": "privacy@tabsira.me",
        "support_email": "support@tabsira.me",
    }


async def test_legal_follows_the_settings(make_settings):
    application = create_app(
        make_settings(
            terms_version="2027-01-01",
            privacy_version="2027-02-01",
            privacy_email="p@example.com",
            support_email="s@example.com",
        )
    )
    async with client_for(application) as http:
        body = (await http.get("/legal")).json()

    assert body == {
        "terms_version": "2027-01-01",
        "privacy_version": "2027-02-01",
        "privacy_email": "p@example.com",
        "support_email": "s@example.com",
    }
