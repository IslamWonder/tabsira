"""
Delete the public photo copies that nothing shows any more.

    uv run python -m src.cli.reconcile_photos

Meant for an hourly systemd timer on one host. A withdrawal or a moderator's removal
answers the person even when the photo store fails; the public copy it should have
deleted then stays until this runs (the API also asks the worker to run it right after the
failure). Every insight with a public copy is checked against what is live now. A second
process started meanwhile steps aside. Exit 0 when every copy is right or the run stepped
aside, 1 when the store still refused some or the database cannot be reached.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError, Settings, load_settings
from src.database import dispose_engine, get_sessionmaker
from src.services.photo_service import reconcile_public_copies
from src.storage.photos import build_photo_store


async def execute(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> int:
    """
    Reconcile the public copies once; return the exit code.

    Without a `session_factory` the application's own engine is used and closed at the end.
    """
    try:
        factory = session_factory or get_sessionmaker()
        async with factory() as db, db.begin():
            report = await reconcile_public_copies(db, build_photo_store(settings))
    except (SQLAlchemyError, OSError) as error:
        sys.stderr.write(
            f"Cannot reconcile the public photo copies ({type(error).__name__}). "
            "Is the database migrated and reachable?\n"
        )
        return 1
    finally:
        if session_factory is None:
            await dispose_engine()
    if report.skipped:
        sys.stdout.write("photos: another reconcile is running; nothing done\n")
        return 0
    sys.stdout.write(
        f"photos: {report.checked} public copies checked, {report.deleted} deleted, "
        f"{report.failed} the store still refused\n"
    )
    return 1 if report.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Reconcile the public copies; return the process exit code."""
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
