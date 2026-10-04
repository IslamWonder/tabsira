"""
Apply the retention and compression settings to the time series (decision 13).

    uv run python -m src.cli.timeseries_policy

The migration sets the policies of `scan_events`, `ai_calls` and
`evidence_exposures` from the settings it found; run this after changing
SCAN_EVENTS_*, AI_CALLS_* or EVIDENCE_EXPOSURES_* to replace them. Exits 0 when
every policy was set, 1 when the database refused.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import Settings, get_settings
from src.database import dispose_engine, get_sessionmaker
from src.models.timeseries import HYPERTABLES, policy_statements


def statements(settings: Settings) -> list[tuple[str, int, int, tuple[str, ...]]]:
    """Return, for each time series, its retention, its compression delay and the statements."""
    plan = []
    for table in HYPERTABLES:
        retention = int(getattr(settings, f"{table}_retention_days"))
        compress = int(getattr(settings, f"{table}_compress_after_days"))
        plan.append((table, retention, compress, policy_statements(table, retention, compress)))
    return plan


async def apply(maker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Replace every policy in one transaction; return the exit code."""
    plan = statements(settings)
    try:
        async with maker() as session, session.begin():
            for _table, _retention, _compress, sqls in plan:
                for sql in sqls:
                    await session.execute(text(sql))
    except SQLAlchemyError as error:
        sys.stderr.write(f"The policies were not changed: {type(error).__name__}\n")
        return 1
    for table, retention, compress, _sqls in plan:
        sys.stdout.write(f"app.{table}: compressed after {compress} days, kept {retention} days\n")
    return 0


async def _main() -> int:
    try:
        return await apply(get_sessionmaker(), get_settings())
    finally:
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    """Apply the policies; `argv` is accepted for symmetry with the other commands."""
    del argv
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
