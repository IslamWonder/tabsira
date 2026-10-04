"""The migration that adds the `privacy` consent kind, and its downgrade."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.test_migrations import APP_CONFIG, alembic, migrated  # noqa: F401

INSERT_CONSENT = text(
    "INSERT INTO app.consents (user_id, kind, version, granted) VALUES (:u, :k, 'v1', true)"
)


async def test_privacy_is_accepted_after_the_migration_and_removed_by_its_downgrade(migrated):  # noqa: F811
    assert alembic(APP_CONFIG, "upgrade", "20261004_160000").returncode == 0
    async with migrated.begin() as connection:
        user_id = (
            await connection.execute(
                text(
                    "INSERT INTO app.users (email, display_name)"
                    " VALUES ('a@example.com', 'A') RETURNING id"
                )
            )
        ).scalar_one()
    with pytest.raises(Exception, match="ck_consents_kind"):
        async with migrated.begin() as connection:
            await connection.execute(INSERT_CONSENT, {"u": user_id, "k": "privacy"})

    assert alembic(APP_CONFIG, "upgrade", "head").returncode == 0
    async with migrated.begin() as connection:
        await connection.execute(INSERT_CONSENT, {"u": user_id, "k": "privacy"})
        await connection.execute(INSERT_CONSENT, {"u": user_id, "k": "terms"})

    assert alembic(APP_CONFIG, "downgrade", "20261004_160000").returncode == 0
    async with migrated.connect() as connection:
        kinds = (await connection.execute(text("SELECT kind FROM app.consents"))).scalars().all()
    assert kinds == ["terms"]
