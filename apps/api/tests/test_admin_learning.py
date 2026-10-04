"""The learning path views: read-only, with one action, which version is the active one."""

from __future__ import annotations

from sqlalchemy import select

from src.models import AuditAction, LearningPathVersion
from tests.support_admin import audit_rows, csrf_of, path_domain, path_unit, path_version


async def seed(db_session):
    db_session.add_all(
        [
            path_version("tabsira-masar-1.0", is_active=True, title="مسار تبصرة"),
            path_version("tabsira-masar-1.1", title="مسار تبصرة، الإصدار التالي"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            path_domain("tabsira-masar-1.0", "T00"),
            path_domain("tabsira-masar-1.0", "T01", position=2, title="النية والعمل"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            path_unit("tabsira-masar-1.0", "T00_01"),
            path_unit("tabsira-masar-1.0", "T01_01", domain_id="T01", title="الإخلاص في العمل"),
        ]
    )
    await db_session.flush()


async def active(db_session):
    rows = await db_session.scalars(
        select(LearningPathVersion.path_version).where(LearningPathVersion.is_active.is_(True))
    )
    return rows.all()


async def activate(http, pks):
    return await http.post(
        f"/admin/learning-path-version/action/activate?pks={pks}",
        data={"csrf_token": await csrf_of(http)},
    )


# ─── Versions ──────────────────────────────────────────────────────


async def test_the_versions_are_listed_with_their_counts_and_which_is_active(admin, db_session):
    http, _ = admin
    await seed(db_session)

    page = await http.get("/admin/learning-path-version/list")

    assert page.status_code == 200
    for expected in ("tabsira-masar-1.0", "tabsira-masar-1.1", "مسار تبصرة", "Domain count"):
        assert expected in page.text
    detail = await http.get("/admin/learning-path-version/details/tabsira-masar-1.0")
    assert "tabsira-masar-1.0.json" in detail.text
    assert "Source sha256" in detail.text


async def test_activating_a_version_switches_the_active_one_and_is_audited(admin, db_session):
    http, me = admin
    await seed(db_session)

    response = await activate(http, "tabsira-masar-1.1")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/admin/learning-path-version/list")
    assert await active(db_session) == ["tabsira-masar-1.1"]
    row = [r for r in await audit_rows(db_session) if r.action is AuditAction.BULK_ACTION][-1]
    assert (row.model, row.admin_user_id) == ("learning-path-version", me.id)
    assert row.details == {"reason": "activate", "count": 1, "ids": ["tabsira-masar-1.1"]}


async def test_activating_the_active_version_leaves_it_active(admin, db_session):
    http, _ = admin
    await seed(db_session)

    await activate(http, "tabsira-masar-1.0")

    assert await active(db_session) == ["tabsira-masar-1.0"]


async def test_activation_takes_exactly_one_known_version(admin, db_session):
    http, _ = admin
    await seed(db_session)

    for pks in ("", "tabsira-masar-1.0,tabsira-masar-1.1", "tabsira-masar-9.9"):
        response = await activate(http, pks)
        assert response.status_code == 303
        assert "error=Select+exactly+one+version+to+activate." in response.headers["location"]

    assert await active(db_session) == ["tabsira-masar-1.0"]


async def test_versions_domains_and_units_cannot_be_created_edited_or_deleted(admin, db_session):
    http, _ = admin
    await seed(db_session)
    token = await csrf_of(http)

    for identity, key in (
        ("learning-path-version", "tabsira-masar-1.0"),
        ("learning-domain", "tabsira-masar-1.0;T00"),
        ("learning-unit", "tabsira-masar-1.0;T00_01"),
    ):
        assert (await http.get(f"/admin/{identity}/create")).status_code == 403
        assert (await http.get(f"/admin/{identity}/edit/{key}")).status_code == 403
        assert (
            await http.delete(
                f"/admin/{identity}/delete?pks={key}", headers={"X-CSRF-Token": token}
            )
        ).status_code == 403
        assert (await http.get(f"/admin/{identity}/export/csv")).status_code == 403


# ─── Domains and units ─────────────────────────────────────────────


async def test_domains_are_listed_searched_and_shown_by_their_two_part_key(admin, db_session):
    http, _ = admin
    await seed(db_session)

    listing = await http.get("/admin/learning-domain/list")
    found = await http.get("/admin/learning-domain/list?search=النية")
    page = await http.get("/admin/learning-domain/details/tabsira-masar-1.0;T01")

    assert "مفاتيح النظر والتعلم" in listing.text
    assert "النية والعمل" in found.text
    assert "مفاتيح النظر والتعلم" not in found.text.split("<tbody>")[-1]
    assert page.status_code == 200
    assert "النية والعمل" in page.text
    assert "Concepts" in page.text


async def test_units_are_listed_searched_and_shown_with_their_evidence_pointers(admin, db_session):
    http, _ = admin
    await seed(db_session)

    listing = await http.get("/admin/learning-unit/list")
    found = await http.get("/admin/learning-unit/list?search=الإخلاص")
    page = await http.get("/admin/learning-unit/details/tabsira-masar-1.0;T00_01")

    assert "يميّز الشيء الظاهر عن التخمين" in listing.text
    assert "الإخلاص في العمل" in found.text
    assert page.status_code == 200
    # A pointer (surah and verse), never the text of a verse.
    assert "quran:2:255" in page.text
    for label in ("Objectives", "Prerequisites", "Evidence refs", "Source anchors"):
        assert label in page.text


async def test_the_learning_views_need_a_session(anon):
    for identity in ("learning-path-version", "learning-domain", "learning-unit"):
        assert (await anon.get(f"/admin/{identity}/list")).status_code == 302
