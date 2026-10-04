"""The command that makes, revokes and resets admins: each change, its audit row and its exit code."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src import clock
from src.cli import make_admin
from src.cli.make_admin import Change, Options, execute
from src.config import ConfigError
from src.models import AdminAuditLog, AdminSession, AdminTotp, AuditAction
from src.services import admin_session_service


@pytest.fixture
def factory(db_session):
    """Sessions on the test's own connection, so the command's commits roll back with the test."""
    return async_sessionmaker(bind=db_session.bind, expire_on_commit=False)


async def run(factory, email="reader@example.com", change=Change.GRANT):
    return await execute(Options(email=email, change=change), factory)


async def audit_rows(db_session):
    return (await db_session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id))).all()


async def test_granting_makes_an_active_account_an_admin_and_audits_it(
    factory, db_session, make_user, capsys
):
    user = await make_user()

    assert await run(factory) == 0

    await db_session.refresh(user)
    assert user.is_admin is True
    (row,) = await audit_rows(db_session)
    assert (row.action, row.admin_user_id, row.details) == (
        AuditAction.ADMIN_GRANTED,
        user.id,
        {"reason": "cli"},
    )
    assert "now an admin" in capsys.readouterr().out


async def test_the_address_is_found_whatever_its_case(factory, db_session, make_user):
    user = await make_user("Reader@Example.com")

    assert await run(factory, email="  READER@example.COM ") == 0

    await db_session.refresh(user)
    assert user.is_admin is True


async def test_granting_an_account_without_a_password_says_how_to_give_it_one(
    factory, make_user, capsys
):
    await make_user(password=None)

    assert await run(factory) == 0

    assert "forgot password" in capsys.readouterr().out


async def test_granting_twice_changes_and_audits_nothing_the_second_time(
    factory, db_session, make_user, capsys
):
    await make_user(is_admin=True)

    assert await run(factory) == 0

    assert "already an admin" in capsys.readouterr().out
    assert await audit_rows(db_session) == []


@pytest.mark.parametrize("column", ["is_active", "deleted_at"])
async def test_a_disabled_or_deleted_account_cannot_be_made_an_admin(
    factory, db_session, make_user, capsys, column
):
    user = await make_user()
    setattr(user, column, False if column == "is_active" else clock.utcnow())
    await db_session.flush()

    assert await run(factory) == 1

    assert "cannot be made an admin" in capsys.readouterr().err
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_an_unknown_address_exits_one_without_saying_more(factory, capsys):
    assert await run(factory, email="nobody@example.com") == 1

    out = capsys.readouterr()
    assert out.err == "No account has this address.\n"
    assert out.out == ""


async def test_revoking_removes_the_flag_the_sessions_and_the_second_factor(
    factory, db_session, make_user, capsys
):
    admin = await make_user(is_admin=True)
    await admin_session_service.create(db_session, user_id=admin.id, ip_hash="ip", user_agent=None)
    db_session.add(AdminTotp(user_id=admin.id, secret_encrypted="secret"))
    await db_session.flush()

    assert await run(factory, change=Change.REVOKE) == 0

    await db_session.refresh(admin)
    assert admin.is_admin is False
    assert (await db_session.scalars(select(AdminSession))).all() == []
    assert (await db_session.scalars(select(AdminTotp))).all() == []
    (row,) = await audit_rows(db_session)
    assert (row.action, row.admin_user_id) == (AuditAction.ADMIN_REVOKED, admin.id)
    assert "Admin rights removed" in capsys.readouterr().out


async def test_revoking_a_plain_account_changes_nothing(factory, db_session, make_user, capsys):
    await make_user()

    assert await run(factory, change=Change.REVOKE) == 0

    assert "not an admin; nothing changed" in capsys.readouterr().out
    assert await audit_rows(db_session) == []


async def test_resetting_the_second_factor_ends_it_and_the_sessions_and_audits_it(
    factory, db_session, make_user, capsys
):
    admin = await make_user(is_admin=True)
    await admin_session_service.create(db_session, user_id=admin.id, ip_hash="ip", user_agent=None)
    db_session.add(AdminTotp(user_id=admin.id, secret_encrypted="secret"))
    await db_session.flush()

    assert await run(factory, change=Change.RESET_TWO_FACTOR) == 0

    await db_session.refresh(admin)
    assert admin.is_admin is True
    assert (await db_session.scalars(select(AdminTotp))).all() == []
    assert (await db_session.scalars(select(AdminSession))).all() == []
    (row,) = await audit_rows(db_session)
    assert row.action is AuditAction.TWO_FACTOR_RESET
    assert "Second factor removed" in capsys.readouterr().out


async def test_resetting_the_second_factor_of_a_plain_account_is_refused(
    factory, make_user, capsys
):
    await make_user()

    assert await run(factory, change=Change.RESET_TWO_FACTOR) == 1

    assert "not an admin" in capsys.readouterr().err


async def test_a_database_that_cannot_be_reached_exits_one_and_names_the_remedy(capsys):
    def broken():
        raise OperationalError("select 1", {}, OSError("refused"))

    assert await execute(Options("a@example.com", Change.GRANT), broken) == 1

    err = capsys.readouterr().err
    assert "Cannot reach the database (OperationalError)" in err
    assert "make migrate" in err


async def test_a_broken_configuration_exits_one_naming_the_key(monkeypatch, capsys):
    def refuse():
        message = "Invalid configuration: DATABASE_URL"
        raise ConfigError(message)

    monkeypatch.setattr(make_admin, "get_sessionmaker", refuse)

    assert await execute(Options("a@example.com", Change.GRANT)) == 1

    assert "DATABASE_URL" in capsys.readouterr().err


async def test_without_a_session_factory_the_engine_is_the_applications_and_is_closed_after(
    monkeypatch, factory, db_session, make_user
):
    closed = []

    async def dispose():
        closed.append(True)

    monkeypatch.setattr(make_admin, "get_sessionmaker", lambda: factory)
    monkeypatch.setattr(make_admin, "dispose_engine", dispose)
    user = await make_user()

    assert await execute(Options("reader@example.com", Change.GRANT)) == 0

    assert closed == [True]
    await db_session.refresh(user)
    assert user.is_admin is True


@pytest.mark.parametrize(
    ("arguments", "change"),
    [
        (["a@example.com"], Change.GRANT),
        (["a@example.com", "--revoke"], Change.REVOKE),
        (["--reset-two-factor", "a@example.com"], Change.RESET_TWO_FACTOR),
    ],
)
def test_the_arguments_choose_the_change(monkeypatch, arguments, change):
    seen = []

    async def fake(options, session_factory=None):
        seen.append(options)
        return 7

    monkeypatch.setattr(make_admin, "execute", fake)

    assert make_admin.main(arguments) == 7
    assert seen == [Options("a@example.com", change)]


def test_revoking_and_resetting_together_is_refused(capsys):
    with pytest.raises(SystemExit) as stopped:
        make_admin.main(["a@example.com", "--revoke", "--reset-two-factor"])

    assert stopped.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
