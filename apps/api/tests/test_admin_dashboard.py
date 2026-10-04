"""The landing page: counts, and nothing that is a record."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from src import clock
from src.admin import dashboard
from src.models import Consent, ConsentKind, Session
from tests.support_admin import (
    audit_rows,
    candidate,
    enable_two_factor,
    entity,
    path_domain,
    path_unit,
    path_version,
)


def stat(page, label):
    """Return the number shown under a label on the dashboard."""
    found = re.search(
        rf'subheader">(?:<a [^>]*>)?{re.escape(label)}(?:</a>)?</div>\s*'
        rf'<div class="h1 mb-0[^"]*">(\d+)</div>',
        page.text,
    )
    assert found, label
    return int(found.group(1))


async def test_the_dashboard_counts_what_the_database_holds(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com")
    await make_user("off@example.com", is_active=False)
    await make_user("gone@example.com", deleted_at=clock.utcnow())
    now = clock.utcnow()
    db_session.add_all(
        [
            Consent(user_id=reader.id, kind=ConsentKind.TERMS, version="v1", granted=True),
            Session(
                token_hash=b"\x01" * 32,
                user_id=reader.id,
                expires_at=now.replace(year=now.year + 1),
                last_seen_at=now,
            ),
            Session(
                token_hash=b"\x02" * 32,
                user_id=reader.id,
                expires_at=now.replace(year=now.year - 1),
                last_seen_at=now,
            ),
            candidate("a"),
            candidate("b", status="accepted"),
            candidate("c", status="rejected"),
            candidate("d"),
            entity("E001"),
            entity("E002", label_norm="x", label_ar="x"),
            path_version("old"),
            path_version("tabsira-masar-1.0", is_active=True, title="مسار تبصرة"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            path_domain(),
            path_domain(domain_id="T01", position=2),
            path_domain("old", "T00"),
        ]
    )
    await db_session.flush()
    db_session.add(path_unit())
    await db_session.flush()

    page = await http.get("/admin/")

    assert page.status_code == 200
    expected = {
        "Accounts": 3,
        "Active accounts": 2,
        "Admins": 1,
        "Live sessions": 1,
        "Consents recorded": 1,
        "Live admin sessions": 1,
        "Candidates to review": 2,
        "Accepted": 1,
        "Rejected": 1,
        "Entities": 2,
        "Path versions": 2,
        "Domains in the active version": 2,
        "Units in the active version": 1,
    }
    for label, number in expected.items():
        assert stat(page, label) == number, label
    assert "Active version: مسار تبصرة (tabsira-masar-1.0)." in page.text


async def test_the_dashboard_says_when_no_version_is_active_and_shows_no_record(admin, make_user):
    http, _ = admin
    await make_user("reader@example.com", display_name="Reader One")

    page = await http.get("/admin/")

    assert "No version of the learning path is active." in page.text
    assert stat(page, "Domains in the active version") == 0
    assert stat(page, "Units in the active version") == 0
    assert "reader@example.com" not in page.text
    assert "Reader One" not in page.text
    assert "Signed in as admin@example.com." in page.text


async def test_the_dashboard_counts_the_last_day_of_the_audit_log(admin, db_session):
    http, _ = admin
    await http.get("/admin/user/list")
    await db_session.execute(
        text(
            "INSERT INTO app.admin_audit_log (at, action) VALUES "
            "(now() - INTERVAL '3 days', 'sign_in_failed'), (now(), 'sign_in_failed')"
        )
    )

    page = await http.get("/admin/")

    assert stat(page, "Failed sign-ins") == 1
    assert stat(page, "Admin sign-ins") == 1
    # The sign-in, the list page and the failed attempt of today; the one of three days ago is out.
    assert stat(page, "Audit events") == 3
    assert "text-danger" in page.text
    assert len(await audit_rows(db_session)) == 4


async def test_the_banner_asks_for_the_second_factor_until_it_is_on(admin, moving_clock):
    http, _ = admin

    before = await http.get("/admin/")
    assert "You have not turned on the second factor." in before.text
    assert 'href="https://api.tabsira.test/admin/two-factor"' in before.text

    await enable_two_factor(http, moving_clock)

    assert "You have not turned on the second factor." not in (await http.get("/admin/")).text


class _Catalogue:
    """Answers the catalogue query with a fixed estimate."""

    def __init__(self, estimate: int | None) -> None:
        self.estimate = estimate

    async def scalar(self, _statement: object) -> int | None:
        return self.estimate


@pytest.mark.parametrize("never_analysed", [-1, None])
async def test_a_table_never_analysed_counts_zero_places(never_analysed):
    # ANALYZE writes its estimate in place and keeps it past a rollback, so a real
    # never-analysed table cannot be counted on once any other test has analysed it.
    assert await dashboard.estimated_geonames(_Catalogue(never_analysed)) == 0  # type: ignore[arg-type]


async def test_the_place_count_is_the_planners_estimate_after_an_analyse(db_session):
    await db_session.execute(
        text("INSERT INTO geodata.geonames (geoname_id, name) VALUES (1, 'A'), (2, 'B')")
    )
    await db_session.execute(text("ANALYZE geodata.geonames"))

    assert await dashboard.estimated_geonames(db_session) == 2
