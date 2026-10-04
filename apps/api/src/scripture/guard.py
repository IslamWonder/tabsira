"""
The one way to write scripture: open the guard for the current transaction.

The database refuses every insert, update and delete on the scripture tables
(`app.scripture_write_guard`) unless the transaction set
`tabsira.scripture_write` to `import` or `sync`. Only the importers and the
correction sync call `allow_scripture_writes`, and the setting ends with their
transaction, so nothing else in the application can change a verse or a hadith.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

WRITE_SETTING = "tabsira.scripture_write"


class WritePurpose(StrEnum):
    """Why scripture is being written; the database accepts these two only."""

    IMPORT = "import"
    SYNC = "sync"


async def allow_scripture_writes(session: AsyncSession, purpose: WritePurpose) -> None:
    """Let the current transaction write scripture; the permission ends with it."""
    await session.execute(
        text("SELECT set_config(:name, :purpose, true)"),
        {"name": WRITE_SETTING, "purpose": purpose.value},
    )
