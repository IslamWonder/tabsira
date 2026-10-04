"""add_timestamp_id

Revision ID: 20261004_170000
Revises: 20261004_160000
Create Date: 2026-10-04 17:00:00.000000

The function that hands out public ids (src/models/public_id.py): time-ordered
64-bit keys for every record that reaches a URL or an API response. Its salt is
drawn here, at upgrade time, and lives only in the database. Each table that uses
it creates its own `app.<table>_id_seq` in the migration that creates the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from src.models.public_id import TIMESTAMP_ID_FUNCTION, new_salt, timestamp_id_function_sql

revision: str = "20261004_170000"
down_revision: str | Sequence[str] | None = "20261004_160000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(timestamp_id_function_sql(new_salt()))


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {TIMESTAMP_ID_FUNCTION}(text)")
