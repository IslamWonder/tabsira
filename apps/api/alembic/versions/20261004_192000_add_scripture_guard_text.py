"""add_scripture_guard_text

Revision ID: 20261004_192000
Revises: 20261004_191000
Create Date: 2026-10-04 19:20:00.000000

The leak guard's skeleton of each verse and hadith (`src.scripture.guard_fold`),
beside the search copy: a quotation in today's spelling and the stored Uthmani
text fold alike there, and not in the search copy. Each gets a trigram index,
and the verse spans are rebuilt on it. The existing rows are filled from the
stored texts with the same fold the importers use. The statements of the spans
are written out here as `src/models/scripture.py` writes them for a schema built
from the models; a test keeps the two identical.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.scripture.guard_fold import guard_fold

revision: str = "20261004_192000"
down_revision: str | Sequence[str] | None = "20261004_191000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "app"
# Search table: (its key, the scripture table it copies).
SEARCH_TABLES = {
    "quran_verse_search": ("verse_id", "quran_verses"),
    "hadith_search": ("hadith_id", "hadiths"),
}
VERSE_SPAN_STATEMENTS = (
    """
    CREATE MATERIALIZED VIEW app.quran_verse_spans AS
    SELECT s.verse_id,
           concat_ws(
               ' ',
               s.guard_text,
               array_to_string(
                   (string_to_array(string_agg(s.guard_text, ' ') OVER following, ' '))[1:6],
                   ' '
               )
           ) AS guard_text
    FROM app.quran_verse_search AS s
    JOIN app.quran_verses AS v ON v.id = s.verse_id
    WINDOW following AS (
        PARTITION BY v.surah ORDER BY v.ayah ROWS BETWEEN 1 FOLLOWING AND 6 FOLLOWING
    )
    """,
    "CREATE UNIQUE INDEX ix_quran_verse_spans_verse_id ON app.quran_verse_spans (verse_id)",
    """
    CREATE INDEX ix_quran_verse_spans_guard_text_trgm
    ON app.quran_verse_spans USING gin (guard_text gin_trgm_ops)
    """,
)
DROP_VERSE_SPANS = "DROP MATERIALIZED VIEW IF EXISTS app.quran_verse_spans"
# The spans as the previous revision built them, on the search copy.
PREVIOUS_SPAN_STATEMENTS = tuple(
    statement.replace("guard_text", "normalized_text") for statement in VERSE_SPAN_STATEMENTS
)
BATCH = 2000


def _fill(table: str, key: str, source: str) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            f"SELECT s.{key}, t.text FROM {SCHEMA}.{table} AS s JOIN {SCHEMA}.{source} AS t ON t.id = s.{key}"
        )
    ).all()
    update = sa.text(f"UPDATE {SCHEMA}.{table} SET guard_text = :guard WHERE {key} = :id")
    for start in range(0, len(rows), BATCH):
        connection.execute(
            update,
            [{"id": row[0], "guard": guard_fold(row[1])} for row in rows[start : start + BATCH]],
        )


def upgrade() -> None:
    op.execute(DROP_VERSE_SPANS)
    for table, (key, source) in SEARCH_TABLES.items():
        op.add_column(table, sa.Column("guard_text", sa.Text(), nullable=True), schema=SCHEMA)
        _fill(table, key, source)
        op.alter_column(table, "guard_text", nullable=False, schema=SCHEMA)
        op.create_index(
            f"ix_{table}_guard_text_trgm",
            table,
            ["guard_text"],
            schema=SCHEMA,
            postgresql_using="gin",
            postgresql_ops={"guard_text": "gin_trgm_ops"},
        )
    for statement in VERSE_SPAN_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(DROP_VERSE_SPANS)
    for table in SEARCH_TABLES:
        op.drop_index(f"ix_{table}_guard_text_trgm", table_name=table, schema=SCHEMA)
        op.drop_column(table, "guard_text", schema=SCHEMA)
    for statement in PREVIOUS_SPAN_STATEMENTS:
        op.execute(statement)
