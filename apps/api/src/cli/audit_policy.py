"""
Apply the audit log's retention and compression windows from the settings.

    uv run python -m src.cli.audit_policy

The migration that creates `app.admin_audit_log` sets both policies from
ADMIN_AUDIT_RETENTION_DAYS and ADMIN_AUDIT_COMPRESS_AFTER_DAYS. Changing the settings
later changes nothing in the database by itself: run this to replace the policies with
the new windows. It is safe to run again. Exits 0 on success and 1 when the settings
are invalid or the database cannot be reached (is it migrated?).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError, Settings, load_settings
from src.database import dispose_engine, get_sessionmaker
from src.models.admin_audit import policy_statements


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


async def execute(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> int:
    """
    Replace the policies with the windows in `settings`; return the exit code.

    Without a `session_factory` the application's own engine is used and closed
    when the policies are set.
    """
    try:
        factory = session_factory or get_sessionmaker()
        async with factory() as db:
            for statement in policy_statements(
                settings.admin_audit_retention_days, settings.admin_audit_compress_after_days
            ):
                await db.execute(text(statement))
            await db.commit()
    except (ConfigError, SQLAlchemyError, OSError) as error:
        sys.stderr.write(
            f"Cannot set the audit log policies ({type(error).__name__}). Is the database migrated? "
            "Run `make migrate`.\n"
        )
        return 1
    finally:
        if session_factory is None:
            await dispose_engine()
    _say(
        f"admin audit log: compressed after {settings.admin_audit_compress_after_days} days, "
        f"kept {settings.admin_audit_retention_days} days"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Apply the policies; return the process exit code."""
    if argv:
        sys.stderr.write("This command takes no arguments.\n")
        return 2
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return asyncio.run(execute(settings))


if __name__ == "__main__":
    raise SystemExit(main())
