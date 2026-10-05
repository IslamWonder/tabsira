"""
Orphan the atlas entries nobody looks after, and widen their public place.

    uv run python -m src.cli.mark_orphans

Meant for a daily systemd timer on one host (decision 60), never once per worker. A published
entry with no open sponsorship and no sign of life for `ORPHAN_AFTER_DAYS` turns orphaned; its
public place widens to its region, city or country, the earlier place is recorded where no route
reads it, and its photo copy goes. A second run the same day finds nothing to do. The output is
counts only, never a place or an entry. Exit 0 when every entry was handled, 1 when one failed
(it is tried again at the next run) or the database cannot be reached.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError, Settings, load_settings
from src.database import dispose_engine, get_sessionmaker
from src.features import FeatureFlag
from src.services.orphan_service import mark_orphans
from src.storage.photos import build_photo_store


async def execute(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession] | None = None
) -> int:
    """
    Mark the quiet entries once; return the exit code.

    Without a `session_factory` the application's own engine is used and closed at the end.
    While sponsoring is switched off nothing is done: an entry nobody can sponsor must not lose
    its place and its author's name for it.
    """
    if not settings.is_enabled(FeatureFlag.ATLAS_SPONSORSHIP):
        sys.stdout.write("orphans: sponsoring is switched off; nothing done\n")
        return 0
    try:
        factory = session_factory or get_sessionmaker()
        report = await mark_orphans(
            factory, settings.orphan_after_days, build_photo_store(settings)
        )
    except (SQLAlchemyError, OSError) as error:
        sys.stderr.write(
            f"Cannot mark the orphaned entries ({type(error).__name__}). "
            "Is the database migrated and reachable?\n"
        )
        return 1
    finally:
        if session_factory is None:
            await dispose_engine()
    sys.stdout.write(
        f"orphans: {report.marked} entries orphaned, {report.widened} places widened, "
        f"{report.failed} failed\n"
    )
    return 1 if report.failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Mark the quiet entries; return the process exit code."""
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
