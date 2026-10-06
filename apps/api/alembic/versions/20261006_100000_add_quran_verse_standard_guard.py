"""add_quran_verse_standard_guard

Revision ID: 20261006_100000
Revises: 20261005_233000
Create Date: 2026-10-06 10:00:00.000000

The leak guard's skeleton of each verse converted into today's spelling (task
05.9): `corpus.quran_verse_standard_guard` keeps, per verse, only the guard
skeleton of the stored quranpedia text after our converter
(`src.scripture.standard_spelling`) and its word count, never a readable text;
`corpus.quran_verse_standard_spans` is the same view of seven-word spans across
verses as `quran_verse_spans`, over it. The rows of a store that is already
there are computed here with the converter of this release; later the importer,
the correction sync and `import_scripture standard` (make data, every deploy)
keep them in line with the text and the converter. The statements of the view
are written out here as `src/models/scripture.py` writes them; a test keeps
them identical.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from src.scripture.standard_spelling import standard_skeleton

revision: str = "20261006_100000"
down_revision: str | Sequence[str] | None = "20261005_233000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "corpus"
TABLE = "quran_verse_standard_guard"
GUARD_WORDS_SQL = "cardinality(string_to_array(guard_text, ' '::text))"

STANDARD_SPAN_STATEMENTS = (
    """
    CREATE MATERIALIZED VIEW corpus.quran_verse_standard_spans AS
    SELECT s.verse_id,
           concat_ws(
               ' ',
               s.guard_text,
               array_to_string(
                   (string_to_array(string_agg(s.guard_text, ' ') OVER following, ' '))[1:6],
                   ' '
               )
           ) AS guard_text
    FROM corpus.quran_verse_standard_guard AS s
    JOIN corpus.quran_verses AS v ON v.id = s.verse_id
    WINDOW following AS (
        PARTITION BY v.surah ORDER BY v.ayah ROWS BETWEEN 1 FOLLOWING AND 6 FOLLOWING
    )
    """,
    """
    CREATE UNIQUE INDEX ix_quran_verse_standard_spans_verse_id
    ON corpus.quran_verse_standard_spans (verse_id)
    """,
    """
    CREATE INDEX ix_quran_verse_standard_spans_guard_text_trgm
    ON corpus.quran_verse_standard_spans USING gin (guard_text gin_trgm_ops)
    """,
)
DROP_STANDARD_SPANS = "DROP MATERIALIZED VIEW IF EXISTS corpus.quran_verse_standard_spans"


def _fill() -> None:
    """Compute the skeleton of every verse already stored (none on a new database)."""
    connection = op.get_bind()
    verses = connection.execute(sa.text("SELECT id, text FROM corpus.quran_verses")).all()
    if verses:
        connection.execute(
            sa.text(f"INSERT INTO {SCHEMA}.{TABLE} (verse_id, guard_text) VALUES (:id, :guard)"),
            [{"id": verse_id, "guard": standard_skeleton(text)} for verse_id, text in verses],
        )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("verse_id", sa.BigInteger(), nullable=False),
        sa.Column("guard_text", sa.Text(), nullable=False),
        sa.Column(
            "guard_words",
            sa.Integer(),
            sa.Computed(GUARD_WORDS_SQL, persisted=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["verse_id"],
            ["corpus.quran_verses.id"],
            name=op.f("fk_quran_verse_standard_guard_verse_id_quran_verses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("verse_id", name=op.f("pk_quran_verse_standard_guard")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_quran_verse_standard_guard_guard_text_trgm",
        TABLE,
        ["guard_text"],
        unique=False,
        schema=SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"guard_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_quran_verse_standard_guard_guard_words", TABLE, ["guard_words"], schema=SCHEMA
    )
    _fill()
    for statement in STANDARD_SPAN_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(DROP_STANDARD_SPANS)
    op.drop_table(TABLE, schema=SCHEMA)
