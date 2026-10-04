"""The users, sessions and consents views: what they show, what they let an admin do, and what never appears."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.models import Consent, ConsentKind, Profile, Session
from src.models.profile import AgeRange, Gender, ReligiousBackground
from tests.support_admin import audit_rows, csrf_of

SECRET_HASH_PREFIX = "$2b$"


async def add_session(db_session, user, token=b"\x01" * 32, agent="Firefox on Linux"):
    now = datetime.now(UTC)
    row = Session(
        token_hash=token,
        user_id=user.id,
        expires_at=now + timedelta(days=1),
        last_seen_at=now,
        ip_hash="f" * 64,
        user_agent=agent,
    )
    db_session.add(row)
    await db_session.flush()
    return row


# ─── Users ─────────────────────────────────────────────────────────


async def test_the_users_list_shows_the_account_columns_and_nothing_private(admin, make_user):
    http, _ = admin
    await make_user("reader@example.com", display_name="Reader One", verified=True)

    page = await http.get("/admin/user/list")

    assert page.status_code == 200
    for expected in ("reader@example.com", "Reader One", "admin@example.com"):
        assert expected in page.text
    for header in ("Email", "Display name", "Is active", "Is admin", "Created at"):
        assert header in page.text
    assert SECRET_HASH_PREFIX not in page.text
    assert "Password" not in page.text


async def test_a_users_page_shows_their_flags_and_dates_but_never_the_password_hash(
    admin, make_user
):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader One", verified=True)

    page = await http.get(f"/admin/user/details/{reader.id}")

    assert page.status_code == 200
    for expected in ("reader@example.com", "Reader One", str(reader.id)):
        assert expected in page.text
    for hidden in ("Password", SECRET_HASH_PREFIX, "password_hash"):
        assert hidden not in page.text


async def test_the_users_list_is_searched_by_address_or_name(admin, make_user):
    http, _ = admin
    await make_user("alpha@example.com", display_name="Alpha")
    await make_user("beta@example.com", display_name="Beta")

    by_email = await http.get("/admin/user/list?search=alpha@")
    by_name = await http.get("/admin/user/list?search=Beta")

    assert "alpha@example.com" in by_email.text
    assert "beta@example.com" not in by_email.text
    assert "beta@example.com" in by_name.text


async def test_a_users_edit_form_has_only_the_name_and_the_active_switch(admin, make_user):
    http, _ = admin
    reader = await make_user("reader@example.com")

    page = await http.get(f"/admin/user/edit/{reader.id}")

    for field in ('name="display_name"', 'name="is_active"'):
        assert field in page.text
    for absent in ("is_admin", "password_hash", 'name="email"', "email_verified_at", "deleted_at"):
        assert absent not in page.text


async def test_an_admin_can_rename_and_deactivate_another_account(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com", display_name="Reader")

    response = await http.post(
        f"/admin/user/edit/{reader.id}",
        data={"display_name": "Renamed", "csrf_token": await csrf_of(http), "save": "Save"},
    )

    assert response.status_code == 302
    await db_session.refresh(reader)
    assert (reader.display_name, reader.is_active) == ("Renamed", False)
    # The switch was left unticked, so the account is off, and nothing else changed.
    assert reader.is_admin is False
    assert reader.email == "reader@example.com"


async def test_an_admin_cannot_deactivate_their_own_account(admin, db_session):
    http, me = admin

    response = await http.post(
        f"/admin/user/edit/{me.id}",
        data={"display_name": "Admin", "csrf_token": await csrf_of(http), "save": "Save"},
    )

    assert response.status_code == 400
    assert "You cannot deactivate your own account." in response.text
    await db_session.refresh(me)
    assert me.is_active is True


async def test_there_is_no_way_to_create_or_delete_an_account_or_to_make_an_admin_here(
    admin, make_user, db_session
):
    http, _ = admin
    reader = await make_user("reader@example.com")
    token = await csrf_of(http)

    assert (await http.get("/admin/user/create")).status_code == 403
    assert (
        await http.post("/admin/user/create", data={"csrf_token": token, "email": "x@example.com"})
    ).status_code == 403
    assert (
        await http.delete(f"/admin/user/delete?pks={reader.id}", headers={"X-CSRF-Token": token})
    ).status_code == 403
    # An edit that sends the flag anyway changes nothing: it is not a field of the form.
    edit = await http.post(
        f"/admin/user/edit/{reader.id}",
        data={"display_name": "R", "is_active": "y", "is_admin": "y", "csrf_token": token},
    )
    assert edit.status_code == 302
    await db_session.refresh(reader)
    assert (reader.display_name, reader.is_admin) == ("R", False)


async def test_the_users_list_never_exports(admin):
    http, _ = admin

    for kind in ("csv", "json"):
        assert (await http.get(f"/admin/user/export/{kind}")).status_code == 403


async def test_a_users_profile_answers_appear_nowhere_in_the_admin(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com")
    profile = await db_session.get(Profile, reader.id)
    profile.religious_background = ReligiousBackground.MUSLIM
    profile.gender = Gender.WOMAN
    profile.age_range = AgeRange.FROM_25_TO_39
    await db_session.flush()

    pages = [
        await http.get("/admin/"),
        await http.get("/admin/user/list"),
        await http.get(f"/admin/user/details/{reader.id}"),
        await http.get(f"/admin/user/edit/{reader.id}"),
    ]

    for page in pages:
        assert page.status_code == 200
        for sensitive in ("muslim", "woman", "25_39", "religious", "gender", "age_range"):
            assert sensitive not in page.text.lower().replace("fa-", ""), sensitive


# ─── Sessions ──────────────────────────────────────────────────────


async def test_the_sessions_list_shows_who_and_when_but_not_the_token_or_the_address(
    admin, make_user, db_session
):
    http, _ = admin
    reader = await make_user("reader@example.com")
    row = await add_session(db_session, reader)

    page = await http.get("/admin/session/list")

    assert page.status_code == 200
    assert str(row.id) in page.text
    assert str(reader.id) in page.text
    assert "Firefox on Linux" in page.text
    for hidden in ("Token hash", "token_hash", "Ip hash", "f" * 64, "\\x01"):
        assert hidden not in page.text


async def test_a_sessions_page_shows_the_same_columns_and_no_token_or_address_hash(
    admin, make_user, db_session
):
    http, _ = admin
    reader = await make_user("reader@example.com")
    row = await add_session(db_session, reader)

    page = await http.get(f"/admin/session/details/{row.id}")

    assert page.status_code == 200
    assert "Firefox on Linux" in page.text
    for hidden in ("Token hash", "token_hash", "Ip hash", "f" * 64):
        assert hidden not in page.text


async def test_sessions_cannot_be_created_edited_or_deleted_by_form(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com")
    row = await add_session(db_session, reader)
    token = await csrf_of(http)

    assert (await http.get("/admin/session/create")).status_code == 403
    assert (await http.get(f"/admin/session/edit/{row.id}")).status_code == 403
    assert (
        await http.delete(f"/admin/session/delete?pks={row.id}", headers={"X-CSRF-Token": token})
    ).status_code == 403


async def test_revoking_sessions_deletes_the_selected_ones_only_and_is_audited(
    admin, make_user, db_session
):
    http, _ = admin
    reader = await make_user("reader@example.com")
    first = await add_session(db_session, reader, token=b"\x01" * 32)
    second = await add_session(db_session, reader, token=b"\x02" * 32)
    kept = await add_session(db_session, reader, token=b"\x03" * 32)

    response = await http.post(
        f"/admin/session/action/revoke?pks={first.id},{second.id},not-a-uuid",
        data={"csrf_token": await csrf_of(http)},
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/admin/session/list")
    remaining = (await db_session.scalars(select(Session.id))).all()
    assert remaining == [kept.id]
    row = [r for r in await audit_rows(db_session) if r.action.value == "bulk_action"][-1]
    assert row.model == "session"
    assert row.details == {
        "reason": "revoke",
        "count": 3,
        "ids": [str(first.id), str(second.id), "not-a-uuid"],
    }


async def test_revoking_with_nothing_selected_says_so_and_deletes_nothing(
    admin, make_user, db_session
):
    http, _ = admin
    reader = await make_user("reader@example.com")
    await add_session(db_session, reader)

    for query in ("", "?pks=", "?pks=not-a-uuid"):
        response = await http.post(
            f"/admin/session/action/revoke{query}", data={"csrf_token": await csrf_of(http)}
        )
        assert response.status_code == 303
        assert "error=Select+at+least+one+record+first." in response.headers["location"]

    assert len((await db_session.scalars(select(Session))).all()) == 1
    page = await http.get("/admin/session/list?error=Select+at+least+one+record+first.")
    assert "Select at least one record first." in page.text


async def test_the_session_list_offers_the_revoke_action_with_a_confirmation(admin, make_user):
    http, _ = admin

    page = await http.get("/admin/session/list")

    assert "action-customconfirm-revoke" in page.text
    assert "Sign the people behind the selected sessions out?" in page.text


# ─── Consents ──────────────────────────────────────────────────────


async def test_consents_are_listed_read_only(admin, make_user, db_session):
    http, _ = admin
    reader = await make_user("reader@example.com")
    db_session.add(Consent(user_id=reader.id, kind=ConsentKind.TERMS, version="v1", granted=True))
    await db_session.flush()

    page = await http.get("/admin/consent/list")

    assert page.status_code == 200
    for expected in (str(reader.id), "terms", "v1"):
        assert expected in page.text
    assert (await http.get("/admin/consent/create")).status_code == 403
    only_terms = await http.get("/admin/consent/list?kind=photo_storage")
    assert "v1" not in only_terms.text.split("<tbody>")[-1]


@pytest.mark.parametrize("path", ["user", "session", "consent"])
async def test_a_signed_out_browser_reaches_none_of_these_views(anon, path):
    response = await anon.get(f"/admin/{path}/list")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


async def test_a_record_that_does_not_exist_is_a_404(admin):
    http, _ = admin

    response = await http.get("/admin/user/details/00000000-0000-7000-8000-000000000000")

    assert response.status_code == 404
