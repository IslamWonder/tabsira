"""create_quran_verse_spans

Revision ID: 20261004_191000
Revises: 20261004_190500
Create Date: 2026-10-04 19:10:00.000000

The folded text of each verse followed by the next six words of its surah, as
a materialized view of the search copies with a trigram index, so the leak
guard finds a quotation of short verses one after another. The importer and
the correction sync rebuild it. The statements are written out here as
`src/models/scripture.py` writes them for a schema built from the models; a
test keeps the two identical.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261004_191000"
down_revision: str | Sequence[str] | None = "20261004_190500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSE_SPAN_STATEMENTS = (
    """
    CREATE MATERIALIZED VIEW app.quran_verse_spans AS
    SELECT s.verse_id,
           concat_ws(
               ' ',
               s.normalized_text,
               array_to_string(
                   (string_to_array(string_agg(s.normalized_text, ' ') OVER following, ' '))[1:6],
                   ' '
               )
           ) AS normalized_text
    FROM app.quran_verse_search AS s
    JOIN app.quran_verses AS v ON v.id = s.verse_id
    WINDOW following AS (
        PARTITION BY v.surah ORDER BY v.ayah ROWS BETWEEN 1 FOLLOWING AND 6 FOLLOWING
    )
    """,
    "CREATE UNIQUE INDEX ix_quran_verse_spans_verse_id ON app.quran_verse_spans (verse_id)",
    """
    CREATE INDEX ix_quran_verse_spans_normalized_text_trgm
    ON app.quran_verse_spans USING gin (normalized_text gin_trgm_ops)
    """,
)
DROP_VERSE_SPANS = "DROP MATERIALIZED VIEW IF EXISTS app.quran_verse_spans"


def upgrade() -> None:
    for statement in VERSE_SPAN_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(DROP_VERSE_SPANS)
