"""Writing the audit log: what a row may hold, and what can never get in."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from src.models import AdminAuditLog, AuditAction
from src.services import admin_audit_service
from src.services.admin_audit_service import details_of, record


def test_details_hold_field_names_a_reason_and_record_ids_only():
    assert details_of(fields=["status", "review_note", "status"]) == {
        "fields": ["review_note", "status"]
    }
    assert details_of(reason="bad_password") == {"reason": "bad_password"}
    assert details_of(ids=["a", "b"]) == {"count": 2, "ids": ["a", "b"]}
    assert details_of() is None


def test_a_bulk_action_lists_a_few_ids_and_counts_them_all():
    ids = [str(number) for number in range(admin_audit_service.MAX_LISTED_IDS + 25)]

    details = details_of(ids=ids)

    assert details is not None
    assert details["count"] == len(ids)
    assert details["ids"] == ids[: admin_audit_service.MAX_LISTED_IDS]


@pytest.mark.parametrize(
    "field", ["a typed value", "reader@example.com", "", "x" * 65, "1st", "name;drop", "نص"]
)
def test_a_field_that_is_not_a_column_name_is_refused_so_a_value_cannot_get_in(field):
    with pytest.raises(ValueError, match="column name"):
        details_of(fields=[field])


@pytest.mark.parametrize("reason", ["Bad Password", "", "reader@example.com", "x" * 65])
def test_a_reason_must_be_a_short_lower_case_code(reason):
    with pytest.raises(ValueError, match="lower-case code"):
        details_of(reason=reason)


async def test_a_row_carries_the_admin_what_was_touched_and_the_hashed_client(db_session):
    admin = uuid.uuid4()

    row = await record(
        db_session,
        action=AuditAction.UPDATE,
        admin_user_id=admin,
        model="ontology-candidate",
        record_id="42",
        fields=["status"],
        ip_hash="f" * 64,
        user_agent="agent/1.0",
    )

    stored = await db_session.scalar(select(AdminAuditLog).where(AdminAuditLog.id == row.id))
    assert stored is not None
    assert (stored.action, stored.admin_user_id, stored.model, stored.record_id) == (
        AuditAction.UPDATE,
        admin,
        "ontology-candidate",
        "42",
    )
    assert stored.details == {"fields": ["status"]}
    assert (stored.ip_hash, stored.user_agent) == ("f" * 64, "agent/1.0")


async def test_a_row_may_name_no_admin_and_no_record_and_a_long_agent_is_cut(db_session):
    row = await record(
        db_session,
        action=AuditAction.SIGN_IN_FAILED,
        user_agent="a" * 1000,
        reason="unknown_account",
    )

    assert row.admin_user_id is None
    assert row.model is None
    assert row.details == {"reason": "unknown_account"}
    assert row.user_agent == "a" * admin_audit_service.USER_AGENT_MAX


async def test_no_agent_is_stored_as_none(db_session):
    row = await record(db_session, action=AuditAction.SIGN_OUT, user_agent="")

    assert row.user_agent is None


async def test_a_view_or_record_longer_than_its_column_is_cut_not_refused(db_session):
    row = await record(
        db_session,
        action=AuditAction.VIEW,
        model="m" * 300,
        record_id="r" * 1000,
        ids=["i" * 1000],
    )

    assert row.model == "m" * admin_audit_service.MODEL_MAX
    assert row.record_id == "r" * admin_audit_service.RECORD_ID_MAX
    assert row.details == {"count": 1, "ids": ["i" * admin_audit_service.RECORD_ID_MAX]}


async def test_a_row_with_nothing_to_say_stores_sql_null_not_a_json_null(db_session):
    await record(db_session, action=AuditAction.LIST, model="user")

    unset = await db_session.scalar(
        text("SELECT count(*) FROM app.admin_audit_log WHERE details IS NULL")
    )
    assert unset == 1


def test_a_reason_may_hold_digits():
    assert details_of(reason="step_2") == {"reason": "step_2"}
