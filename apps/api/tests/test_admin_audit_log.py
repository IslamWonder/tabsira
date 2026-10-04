"""The admin audit log table: a hypertable, append-only, with its policies."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from alembic import op
from src.models import AdminAuditLog, AuditAction
from src.models import admin_audit as model

MIGRATION = next(
    (Path(__file__).resolve().parents[1] / "alembic" / "versions").glob(
        "*_create_admin_audit_log.py"
    )
)


async def add(db_session, **values):
    row = AdminAuditLog(action=values.pop("action", AuditAction.VIEW), **values)
    db_session.add(row)
    await db_session.flush()
    return row


async def scalar(db_session, sql, **params):
    return (await db_session.execute(text(sql), params)).scalar_one()


async def test_the_table_is_a_hypertable_partitioned_on_its_time_column(db_session):
    dimension = await scalar(
        db_session,
        """
        SELECT column_name FROM timescaledb_information.dimensions
        WHERE hypertable_schema = 'app' AND hypertable_name = 'admin_audit_log'
        """,
    )
    key = (
        await db_session.execute(
            text(
                """
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
                WHERE i.indrelid = 'app.admin_audit_log'::regclass AND i.indisprimary
                """
            )
        )
    ).scalars()

    assert dimension == "at"
    assert set(key) == {"at", "id"}


async def test_the_default_retention_and_compression_policies_are_set(db_session):
    jobs = {
        row.proc_name: row.config
        for row in (
            await db_session.execute(
                text(
                    """
                    SELECT proc_name, config FROM timescaledb_information.jobs
                    WHERE hypertable_schema = 'app' AND hypertable_name = 'admin_audit_log'
                    """
                )
            )
        )
    }

    assert jobs["policy_retention"]["drop_after"] == "400 days"
    assert jobs["policy_compression"]["compress_after"] == "30 days"


async def test_a_row_can_be_added_and_gets_its_time_and_identity(db_session):
    row = await add(db_session, details={"fields": ["status"]}, model="ontology-candidate")

    assert row.at is not None
    assert row.id >= 1
    found = await db_session.scalar(select(AdminAuditLog).where(AdminAuditLog.id == row.id))
    assert found is not None
    assert found.details == {"fields": ["status"]}


async def test_a_row_can_be_neither_changed_nor_deleted(db_session):
    await add(db_session)

    for statement in (
        "UPDATE app.admin_audit_log SET model = 'x'",
        "DELETE FROM app.admin_audit_log",
    ):
        with pytest.raises(IntegrityError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(statement))

    assert await scalar(db_session, "SELECT count(*) FROM app.admin_audit_log") == 1


async def test_the_database_refuses_an_action_it_does_not_know(db_session):
    with pytest.raises(IntegrityError, match="ck_admin_audit_log_action"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO app.admin_audit_log (action) VALUES ('wipe')")
            )


async def test_the_retention_job_still_removes_old_rows_by_dropping_chunks(db_session):
    await db_session.execute(
        text(
            "INSERT INTO app.admin_audit_log (at, action) "
            "VALUES (now() - INTERVAL '500 days', 'view'), (now(), 'view')"
        )
    )

    await db_session.execute(
        text("SELECT drop_chunks('app.admin_audit_log', older_than => INTERVAL '400 days')")
    )

    assert await scalar(db_session, "SELECT count(*) FROM app.admin_audit_log") == 1


async def test_a_compressed_chunk_keeps_its_rows_and_stays_append_only(db_session):
    await db_session.execute(
        text(
            "INSERT INTO app.admin_audit_log (at, action) VALUES (now() - INTERVAL '60 days', 'view')"
        )
    )

    await db_session.execute(
        text(
            "SELECT compress_chunk(chunk) "
            "FROM show_chunks('app.admin_audit_log', older_than => INTERVAL '30 days') AS chunk"
        )
    )

    assert await scalar(db_session, "SELECT count(*) FROM app.admin_audit_log") == 1
    with pytest.raises((IntegrityError, DBAPIError), match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE app.admin_audit_log SET model = 'x'"))


async def test_the_policies_can_be_replaced_with_other_windows(db_session):
    for statement in model.policy_statements(retention_days=100, compress_after_days=10):
        await db_session.execute(text(statement))

    jobs = {
        row.proc_name: row.config
        for row in await db_session.execute(
            text(
                "SELECT proc_name, config FROM timescaledb_information.jobs "
                "WHERE hypertable_name = 'admin_audit_log'"
            )
        )
    }
    assert jobs["policy_retention"]["drop_after"] == "100 days"
    assert jobs["policy_compression"]["compress_after"] == "10 days"


def squash(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_the_migration_and_the_model_build_the_same_hypertable(monkeypatch):
    spec = importlib.util.spec_from_file_location("admin_audit_migration", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements: list[str] = []
    monkeypatch.setattr(op, "f", lambda name: name, raising=False)
    monkeypatch.setattr(op, "create_table", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(op, "create_index", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(op, "execute", statements.append, raising=False)

    migration.upgrade()

    from_model = [
        *model.HYPERTABLE_STATEMENTS,
        *(
            statement
            for statement in model.policy_statements(400, 30)
            if "remove_" not in statement
        ),
    ]
    assert [squash(statement) for statement in statements] == [
        squash(statement) for statement in from_model
    ]
    assert set(migration.ACTIONS) == {action.value for action in AuditAction}


def test_the_log_names_no_column_that_could_hold_what_an_admin_typed():
    names = {column.name for column in AdminAuditLog.__table__.columns}

    assert names == {
        "at",
        "id",
        "admin_user_id",
        "action",
        "model",
        "record_id",
        "details",
        "ip_hash",
        "user_agent",
    }
    # An address or an e-mail never goes in; a keyed hash does.
    assert not {name for name in names if "email" in name or name in {"ip", "ip_address"}}
