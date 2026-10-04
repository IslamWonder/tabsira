"""
What the admin writes to the audit log while it is used: pages, edits, actions.

Sign-in, failed sign-in and sign-out are covered with the sign-in tests. Here: that a list
page, a record page, an edit and a bulk action each leave one row, that a row names
fields and never values, and that the log's own list is read-only.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqladmin.audit import AuditEntry
from starlette.requests import Request

from src.admin.audit import CHANGED_FIELDS_ATTR, AdminAuditBackend, AuditTrail
from src.admin.base import AdminView
from src.models import AuditAction
from tests.support_admin import audit_rows, csrf_of


def fake_request(method="GET", path="/admin/user/list", query="", admin_id=None):
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "root_path": "/admin",
            "query_string": query.encode(),
            "headers": [(b"user-agent", b"pytest")],
            "client": ("203.0.113.9", 4000),
        }
    )
    if admin_id is not None:
        request.state.sqladmin_user_id = str(admin_id)
    return request


@pytest.fixture
def trail(admin_app, admin_maker):
    return AuditTrail(admin_app.state.settings, admin_maker)


async def after_sign_in(db_session):
    """The audit rows written after the sign-in row."""
    return (await audit_rows(db_session))[1:]


# ─── Pages ─────────────────────────────────────────────────────────


async def test_a_list_page_leaves_a_row_without_the_search_term(admin, db_session):
    http, me = admin

    await http.get("/admin/user/list?search=somebody@example.com&sortBy=email&sort=asc")

    (row,) = await after_sign_in(db_session)
    assert (row.action, row.admin_user_id, row.model) == (AuditAction.LIST, me.id, "user")
    assert row.record_id is None
    assert row.details is None
    assert "somebody@example.com" not in repr((row.details, row.model, row.record_id))


async def test_a_record_page_leaves_a_row_naming_the_record(admin, make_user, db_session):
    http, me = admin
    reader = await make_user("reader@example.com")

    await http.get(f"/admin/user/details/{reader.id}")

    (row,) = await after_sign_in(db_session)
    assert (row.action, row.admin_user_id, row.model, row.record_id) == (
        AuditAction.VIEW,
        me.id,
        "user",
        str(reader.id),
    )
    assert row.ip_hash is not None
    assert row.user_agent is not None


async def test_pages_that_are_not_a_list_or_a_record_leave_no_row(admin, db_session):
    http, _ = admin

    await http.get("/admin/")
    await http.get("/admin/two-factor")
    await http.get("/admin/statics/css/tabsira-admin.css")
    await http.get("/admin/user/details/")

    assert await after_sign_in(db_session) == []


async def test_a_page_a_view_refuses_is_still_recorded_as_an_attempt(admin, db_session):
    http, _ = admin

    refused = await http.get("/admin/user/details/00000000-0000-7000-8000-000000000000")

    assert refused.status_code == 404
    (row,) = await after_sign_in(db_session)
    assert row.action is AuditAction.VIEW


# ─── Edits ─────────────────────────────────────────────────────────


async def test_an_edit_leaves_one_row_naming_only_the_fields_that_changed(
    admin, make_user, db_session
):
    http, me = admin
    reader = await make_user("reader@example.com", display_name="Reader")

    await http.post(
        f"/admin/user/edit/{reader.id}",
        data={
            "display_name": "A brand new typed value",
            "is_active": "y",
            "csrf_token": await csrf_of(http),
        },
    )

    update = [row for row in await after_sign_in(db_session) if row.action is AuditAction.UPDATE]
    (row,) = update
    assert (row.admin_user_id, row.model, row.record_id) == (me.id, "user", str(reader.id))
    assert row.details == {"fields": ["display_name"]}
    for stored in await audit_rows(db_session):
        assert "A brand new typed value" not in repr(stored.details)


async def test_an_edit_that_changes_nothing_names_no_field(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader")

    await http.post(
        f"/admin/user/edit/{reader.id}",
        data={"display_name": "Reader", "is_active": "y", "csrf_token": await csrf_of(http)},
    )

    (row,) = [r for r in await after_sign_in(db_session) if r.action is AuditAction.UPDATE]
    assert row.details is None


async def test_an_edit_refused_by_the_view_leaves_no_update_row(admin, db_session):
    http, me = admin

    refused = await http.post(
        f"/admin/user/edit/{me.id}",
        data={"display_name": "Admin", "csrf_token": await csrf_of(http)},
    )

    assert refused.status_code == 400
    assert not [r for r in await audit_rows(db_session) if r.action is AuditAction.UPDATE]


# ─── The hook sqladmin calls for create, update and delete ─────────


async def test_the_hook_writes_create_update_and_delete_rows_with_names_only(trail, db_session):
    admin_id = uuid.uuid4()
    backend = AdminAuditBackend(trail)
    request = fake_request("POST", admin_id=admin_id)

    await backend.log(
        AuditEntry(action="create", identity="widget", pk="7", changes={"name": "x", "size": 1}),
        request,
    )
    await backend.log(AuditEntry(action="delete", identity="widget", pk="7", changes=None), request)
    setattr(request.state, CHANGED_FIELDS_ATTR, ["size"])
    await backend.log(
        AuditEntry(action="update", identity="widget", pk="7", changes={"name": "x", "size": 2}),
        request,
    )

    created, deleted, updated = await audit_rows(db_session)
    assert (created.action, created.details) == (AuditAction.CREATE, {"fields": ["name", "size"]})
    assert (deleted.action, deleted.details) == (AuditAction.DELETE, None)
    assert (updated.action, updated.details) == (AuditAction.UPDATE, {"fields": ["size"]})
    for row in (created, deleted, updated):
        assert (row.admin_user_id, row.model, row.record_id) == (admin_id, "widget", "7")
    # What was typed (the values) is nowhere in them.
    assert "x" not in repr([row.details for row in (created, deleted, updated)]).replace(
        "fields", ""
    )


async def test_the_hook_leaves_out_a_name_that_is_not_a_column_instead_of_losing_the_row(
    trail, db_session
):
    await AdminAuditBackend(trail).log(
        AuditEntry(
            action="create",
            identity="widget",
            pk="1",
            changes={"name": "x", "not a column name": "y", 7: "z"},
        ),
        fake_request("POST", admin_id=uuid.uuid4()),
    )

    (row,) = await audit_rows(db_session)
    assert row.details == {"fields": ["name"]}


async def test_the_hook_without_a_known_admin_writes_a_row_without_one(trail, db_session):
    await AdminAuditBackend(trail).log(
        AuditEntry(action="delete", identity="widget", pk=None), fake_request("DELETE")
    )

    (row,) = await audit_rows(db_session)
    assert (row.admin_user_id, row.record_id) == (None, None)


# ─── What counts as a page, a record or an action ──────────────────


@pytest.mark.parametrize(
    ("method", "path", "action"),
    [
        ("GET", "/admin/user/list", AuditAction.LIST),
        ("GET", "/admin/user/details/abc", AuditAction.VIEW),
        ("GET", "/admin/learning-unit/details/v1;U001", AuditAction.VIEW),
        ("POST", "/admin/session/action/revoke", AuditAction.BULK_ACTION),
    ],
)
async def test_the_trail_recognises_lists_records_and_actions_by_their_address(
    trail, db_session, method, path, action
):
    await trail.access(fake_request(method, path), uuid.uuid4())

    (row,) = await audit_rows(db_session)
    assert row.action is action


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/admin/user/list"),
        ("GET", "/admin/user/list/extra"),
        ("POST", "/admin/user/details/abc"),
        ("GET", "/admin/user/details"),
        ("GET", "/admin/session/action/revoke"),
        ("POST", "/admin/session/action"),
        ("GET", "/admin/user/edit/abc"),
        ("GET", "/admin"),
        ("GET", "/admin/"),
    ],
)
async def test_the_trail_ignores_everything_else(trail, db_session, method, path):
    await trail.access(fake_request(method, path), uuid.uuid4())

    assert await audit_rows(db_session) == []


async def test_a_bulk_action_names_its_records_and_an_empty_selection_names_none(trail, db_session):
    admin_id = uuid.uuid4()

    await trail.access(
        fake_request("POST", "/admin/ontology-candidate/action/accept", "pks=3,4,,5"), admin_id
    )
    await trail.access(fake_request("POST", "/admin/ontology-candidate/action/reject"), admin_id)

    first, second = await audit_rows(db_session)
    assert first.details == {"reason": "accept", "count": 3, "ids": ["3", "4", "5"]}
    assert second.details == {"reason": "reject"}
    assert (first.model, first.admin_user_id) == ("ontology-candidate", admin_id)


async def test_an_address_below_the_admin_is_read_relative_to_its_root(trail, db_session):
    # The same path mounted at another place is still seen as a list of a model.
    request = fake_request("GET", "/backoffice/user/list")
    request.scope["root_path"] = "/backoffice"

    await trail.access(request, uuid.uuid4())

    (row,) = await audit_rows(db_session)
    assert row.model == "user"


async def test_a_created_record_names_every_submitted_field_and_an_edit_only_the_changed_ones(
    admin_app,
):
    # The base class's rule, applied on behalf of any view that inherits it.
    view = admin_app.state.admin.views[0]
    created, edited = fake_request("POST"), fake_request("POST")
    record = SimpleNamespace(name="old", size=1)

    await AdminView.on_model_change(view, {"size": 1, "name": "x"}, record, True, created)
    await AdminView.on_model_change(view, {"size": 1, "name": "new"}, record, False, edited)

    assert getattr(created.state, CHANGED_FIELDS_ATTR) == ["name", "size"]
    assert getattr(edited.state, CHANGED_FIELDS_ATTR) == ["name"]


async def test_an_address_that_names_nothing_real_is_a_404_and_is_recorded_cut_to_size(
    admin, db_session
):
    http, _ = admin

    response = await http.get(f"/admin/{'x' * 200}/list")

    assert response.status_code == 404
    (row,) = await after_sign_in(db_session)
    assert row.model == "x" * 64


@pytest.mark.parametrize(
    ("slug", "reason"),
    [("Revoke-All", "revoke_all"), ("step-2", "step_2"), ("a b!", "ab"), ("***", None)],
)
async def test_an_action_name_in_an_address_is_made_into_a_reason_code(
    trail, db_session, slug, reason
):
    await trail.access(fake_request("POST", f"/admin/user/action/{slug}"), uuid.uuid4())

    (row,) = await audit_rows(db_session)
    assert row.details == ({"reason": reason} if reason else None)
