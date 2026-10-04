"""
Apply quranpedia's corrections to the stored Quran text (decision 16).

    uv run python -m src.cli.sync_quran [--cache-dir DIR]

Meant for a daily systemd timer on one host. Reads the changes feed since the
last successful sync, refetches the changed verses of mushaf 2 and applies
them, all in one transaction. A second process started meanwhile steps aside.
Exit 0 when the sync succeeded or stepped aside, 1 when it failed (nothing is
stored then, and the next run starts from the same date).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database import dispose_engine, get_sessionmaker
from src.scripture.errors import ScriptureError
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.paths import DEFAULT_CACHE_DIR
from src.scripture.quran_sync import sync_quran
from src.scripture.quranpedia import QuranpediaClient, new_http_client


async def run(
    argv: Sequence[str] | None = None,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    http: httpx.AsyncClient | None = None,
) -> int:
    """Run one sync; return the process exit code."""
    parser = argparse.ArgumentParser(description="Apply quranpedia's Quran text corrections.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    args = parser.parse_args(argv)
    maker = sessionmaker or get_sessionmaker()
    try:
        async with http or new_http_client() as client, maker() as session, session.begin():
            await allow_scripture_writes(session, WritePurpose.SYNC)
            report = await sync_quran(session, QuranpediaClient(client), cache_dir=args.cache_dir)
    except ScriptureError as error:
        sys.stderr.write(f"sync failed: {error}\n")
        return 1
    finally:
        if sessionmaker is None:
            await dispose_engine()
    if report.skipped:
        sys.stdout.write("sync: another sync is running; nothing done\n")
        return 0
    via = f", from dump {report.via_dump}" if report.via_dump else ""
    sys.stdout.write(
        f"sync: since {report.since}, {report.changed_rows} changed verses of mushaf 2{via}, "
        f"{report.corrected} corrected ({', '.join(report.corrections) or 'none'}), "
        f"{report.unchanged} unchanged; next run from {report.until[:10]}\n"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
