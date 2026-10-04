"""GET /legal: public, revalidated, the versions and the addresses from the settings."""

from __future__ import annotations

from src.main import create_app
from tests.helpers import client_for


async def test_legal_needs_no_session_and_is_revalidated_every_time(client):
    response = await client.get("/legal")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.json() == {
        "terms_version": "2026-10-04T20:00Z",
        "privacy_version": "2026-10-04T23:00Z",
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
