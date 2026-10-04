"""add_quran_verse_guard_words

Revision ID: 20261004_192700
Revises: 20261004_192500
Create Date: 2026-10-04 19:27:00.000000

How many words each verse's guard skeleton has, computed by the database and
indexed, so the leak guard can hold a short verse (three to six words) against
model text whole, without a run of seven words to look for. The expression is
the one `src/models/scripture.py` gives the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.models.scripture import GUARD_WORDS_SQL

revision: str = "20261004_192700"
down_revision: str | Sequence[str] | None = "20261004_192500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
TABLE = "quran_verse_search"
INDEX = "ix_quran_verse_search_guard_words"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "guard_words",
            sa.Integer(),
            sa.Computed(GUARD_WORDS_SQL, persisted=True),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.create_index(INDEX, TABLE, ["guard_words"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE, schema=SCHEMA)
    op.drop_column(TABLE, "guard_words", schema=SCHEMA)
