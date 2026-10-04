"""The migration that lets `login_attempts` hold the support form's attempts."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.test_migrations import APP_CONFIG, alembic, migrated  # noqa: F401

INSERT = text("INSERT INTO app.login_attempts (kind, ip_hash, succeeded) VALUES (:k, 'ip', true)")


async def test_support_attempts_need_the_migration_and_go_with_its_downgrade(migrated):  # noqa: F811
    assert alembic(APP_CONFIG, "upgrade", "20261004_181000").returncode == 0
    with pytest.raises(Exception, match="ck_login_attempts_kind"):
        async with migrated.begin() as connection:
            await connection.execute(INSERT, {"k": "support"})

    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    async with migrated.begin() as connection:
        await connection.execute(INSERT, {"k": "support"})
        await connection.execute(INSERT, {"k": "login"})

    assert alembic(APP_CONFIG, "downgrade", "20261004_181000").returncode == 0
    async with migrated.connect() as connection:
        kinds = (
            (await connection.execute(text("SELECT kind FROM app.login_attempts"))).scalars().all()
        )
    assert kinds == ["login"]
