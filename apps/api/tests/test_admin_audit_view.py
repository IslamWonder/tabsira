"""The audit log as the admin sees it: a list, newest first, that nothing can change."""

from __future__ import annotations

from tests.support_admin import csrf_of


def rows_of(page):
    """The table body of a list page, without the filters and the menu around it."""
    return page.text.split("<tbody>")[1].split("</tbody>")[0]


async def test_the_log_lists_the_newest_rows_first_with_what_was_touched(admin, make_user):
    http, me = admin
    reader = await make_user("reader@example.com")
    await http.get(f"/admin/user/details/{reader.id}")
    await http.get("/admin/consent/list")

    page = await http.get("/admin/admin-audit-log/list")

    assert page.status_code == 200
    body = page.text
    for header in ("At", "Admin user id", "Action", "Model", "Record id", "Details", "Ip hash"):
        assert header in body
    assert str(me.id) in body
    assert str(reader.id) in body
    # The sign-in is the oldest row, so it comes after the later pages.
    assert body.index("consent") < body.index("sign_in")


async def test_the_log_is_filtered_by_action_and_searched_by_model_or_record(admin, make_user):
    http, _ = admin
    reader = await make_user("reader@example.com")
    await http.get(f"/admin/user/details/{reader.id}")
    await http.get("/admin/consent/list")

    views = await http.get("/admin/admin-audit-log/list?action=view")
    by_model = await http.get("/admin/admin-audit-log/list?search=consent")
    by_record = await http.get(f"/admin/admin-audit-log/list?search={reader.id}")

    assert "sign_in" not in rows_of(views)
    assert str(reader.id) in rows_of(views)
    assert "consent" in rows_of(by_model)
    assert str(reader.id) not in rows_of(by_model)
    assert str(reader.id) in rows_of(by_record)
    assert "consent" not in rows_of(by_record)


async def test_a_rows_details_are_shown_as_names_not_values(admin, make_user):
    http, _ = admin
    reader = await make_user("reader@example.com")
    await http.post(
        f"/admin/user/edit/{reader.id}",
        data={"display_name": "Another", "is_active": "y", "csrf_token": await csrf_of(http)},
    )

    page = await http.get("/admin/admin-audit-log/list?action=update")

    assert "display_name" in page.text
    assert "Another" not in page.text


async def test_the_log_has_no_record_page_no_forms_and_no_export(admin):
    http, _ = admin
    token = await csrf_of(http)

    assert (await http.get("/admin/admin-audit-log/details/anything")).status_code == 403
    assert (await http.get("/admin/admin-audit-log/create")).status_code == 403
    assert (await http.get("/admin/admin-audit-log/edit/anything")).status_code == 403
    assert (await http.get("/admin/admin-audit-log/export/csv")).status_code == 403
    assert (
        await http.delete("/admin/admin-audit-log/delete?pks=1", headers={"X-CSRF-Token": token})
    ).status_code == 403


async def test_the_log_needs_a_session(anon):
    response = await anon.get("/admin/admin-audit-log/list")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
