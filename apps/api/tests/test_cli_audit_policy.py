"""The command that re-applies the audit log's retention and compression windows."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.cli import audit_policy


@pytest.fixture
def factory(db_session):
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


async def windows(db_session):
    return {
        row.proc_name: row.config
        for row in await db_session.execute(
            text(
                "SELECT proc_name, config FROM timescaledb_information.jobs "
                "WHERE hypertable_name = 'admin_audit_log'"
            )
        )
    }


async def test_the_windows_in_the_settings_replace_the_policies(
    factory, db_session, make_settings, capsys
):
    settings = make_settings(admin_audit_retention_days=200, admin_audit_compress_after_days=14)

    assert await audit_policy.execute(settings, factory) == 0

    jobs = await windows(db_session)
    assert jobs["policy_retention"]["drop_after"] == "200 days"
    assert jobs["policy_compression"]["compress_after"] == "14 days"
    assert "compressed after 14 days, kept 200 days" in capsys.readouterr().out


async def test_running_it_again_changes_nothing(factory, db_session, make_settings):
    settings = make_settings()

    assert await audit_policy.execute(settings, factory) == 0
    assert await audit_policy.execute(settings, factory) == 0

    jobs = await windows(db_session)
    assert len(jobs) == 2
    assert jobs["policy_retention"]["drop_after"] == "400 days"


async def test_a_database_that_is_not_migrated_exits_one_and_says_how_to_fix_it(
    make_settings, capsys
):
    def broken():
        raise OperationalError("select 1", {}, OSError("refused"))

    assert await audit_policy.execute(make_settings(), broken) == 1

    err = capsys.readouterr().err
    assert "Cannot set the audit log policies (OperationalError)" in err
    assert "make migrate" in err


async def test_without_a_factory_the_application_engine_is_used_and_closed(
    monkeypatch, factory, make_settings
):
    closed = []

    async def dispose():
        closed.append(True)

    monkeypatch.setattr(audit_policy, "get_sessionmaker", lambda: factory)
    monkeypatch.setattr(audit_policy, "dispose_engine", dispose)

    assert await audit_policy.execute(make_settings()) == 0
    assert closed == [True]


def test_main_loads_the_settings_and_runs(monkeypatch, make_settings):
    seen = []

    async def fake(settings, session_factory=None):
        seen.append(settings)
        return 0

    monkeypatch.setattr(audit_policy, "execute", fake)
    monkeypatch.setattr(audit_policy, "load_settings", make_settings)

    assert audit_policy.main([]) == 0
    assert len(seen) == 1


def test_main_refuses_arguments_and_a_broken_configuration(monkeypatch, capsys):
    assert audit_policy.main(["--now"]) == 2
    assert "takes no arguments" in capsys.readouterr().err

    monkeypatch.setenv("ADMIN_AUDIT_RETENTION_DAYS", "7")

    assert audit_policy.main([]) == 1
    assert "ADMIN_AUDIT_RETENTION_DAYS" in capsys.readouterr().err
