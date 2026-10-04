"""The admin sessions and second-factor tables: constraints, defaults and what leaves with an account."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.models import AdminSession, AdminTotp, User


async def make_user(db_session, email="admin@example.com"):
    user = User(email=email, display_name="Admin", is_admin=True)
    db_session.add(user)
    await db_session.flush()
    return user


def session_row(user, token=b"\x01" * 32):
    now = datetime.now(UTC)
    return AdminSession(
        token_hash=token, user_id=user.id, expires_at=now + timedelta(hours=12), last_seen_at=now
    )


async def test_an_admin_session_has_a_time_ordered_id_and_no_address(db_session):
    user = await make_user(db_session)
    row = session_row(user)
    db_session.add(row)
    await db_session.flush()

    assert row.id.version == 7
    assert row.created_at is not None
    assert row.ip_hash is None
    assert row.user_agent is None
    assert {column.name for column in AdminSession.__table__.columns} == {
        "id",
        "token_hash",
        "user_id",
        "created_at",
        "expires_at",
        "last_seen_at",
        "ip_hash",
        "user_agent",
    }


async def test_an_admin_session_token_hash_is_unique_and_exactly_32_bytes(db_session):
    user = await make_user(db_session)
    db_session.add(session_row(user))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_admin_sessions_token_hash"):
        async with db_session.begin_nested():
            db_session.add(session_row(user))
            await db_session.flush()
    with pytest.raises(IntegrityError, match="ck_admin_sessions_token_hash_length"):
        async with db_session.begin_nested():
            db_session.add(session_row(user, token=b"short"))
            await db_session.flush()


async def test_a_second_factor_starts_unconfirmed_with_no_recovery_codes(db_session):
    user = await make_user(db_session)
    db_session.add(AdminTotp(user_id=user.id, secret_encrypted="gAAAA-not-the-secret"))
    await db_session.flush()

    row = await db_session.get(AdminTotp, user.id, populate_existing=True)

    assert row is not None
    assert row.enabled_at is None
    assert row.last_used_step is None
    assert row.recovery_hashes == []
    assert row.created_at is not None


async def test_an_admin_has_one_second_factor(db_session):
    user = await make_user(db_session)
    db_session.add(AdminTotp(user_id=user.id, secret_encrypted="one"))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="pk_admin_totp"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO app.admin_totp (user_id, secret_encrypted) VALUES (:id, 'two')"),
                {"id": user.id},
            )


async def test_deleting_the_account_deletes_its_admin_sessions_and_second_factor(db_session):
    user = await make_user(db_session)
    db_session.add_all([session_row(user), AdminTotp(user_id=user.id, secret_encrypted="secret")])
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": user.id})

    for table in ("admin_sessions", "admin_totp"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one()  # noqa: S608
        assert count == 0, table
