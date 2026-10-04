"""move_reference_data_to_corpus

Revision ID: 20261004_209000
Revises: 20261004_208000
Create Date: 2026-10-04 22:50:00.000000

The scripture reference data, the world ontology and the learning path move from
`app` into their own `corpus` schema, so they can be exported and installed as one
verified archive (docs/CORPUS.md, decision 57). `ALTER TABLE ... SET SCHEMA` moves
each table with its indexes, constraints, identity sequences and triggers, without
copying a row; the keys that point at them from `app` and `vectors` follow. What
editors and the production jobs write stays in `app`: the hadith rulings, the
verification queue, the scripture audit log, the sync state, the ontology
candidates and every learner's state.

The verse spans are a materialized view over two of the moved tables: it is
dropped and built again in `corpus`. The statements are written out here as
`src/models/scripture.py` writes them; a test keeps the two identical. The
downgrade moves everything back and leaves the schema itself, as it leaves `app`.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261004_209000"
down_revision: str | Sequence[str] | None = "20261004_208000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "corpus"
PREVIOUS_SCHEMA = "app"
# Parents before children, so the downgrade can walk the list backwards.
TABLES = (
    "quran_surahs",
    "quran_verses",
    "quran_verse_history",
    "quran_verse_search",
    "quran_annotations",
    "hadith_collections",
    "hadiths",
    "hadith_search",
    "hadith_signals",
    "ontology_entities",
    "learning_path_versions",
    "learning_domains",
    "learning_units",
)

VERSE_SPAN_STATEMENTS = (
    """
    CREATE MATERIALIZED VIEW corpus.quran_verse_spans AS
    SELECT s.verse_id,
           concat_ws(
               ' ',
               s.guard_text,
               array_to_string(
                   (string_to_array(string_agg(s.guard_text, ' ') OVER following, ' '))[1:6],
                   ' '
               )
           ) AS guard_text
    FROM corpus.quran_verse_search AS s
    JOIN corpus.quran_verses AS v ON v.id = s.verse_id
    WINDOW following AS (
        PARTITION BY v.surah ORDER BY v.ayah ROWS BETWEEN 1 FOLLOWING AND 6 FOLLOWING
    )
    """,
    "CREATE UNIQUE INDEX ix_quran_verse_spans_verse_id ON corpus.quran_verse_spans (verse_id)",
    """
    CREATE INDEX ix_quran_verse_spans_guard_text_trgm
    ON corpus.quran_verse_spans USING gin (guard_text gin_trgm_ops)
    """,
)
DROP_VERSE_SPANS = "DROP MATERIALIZED VIEW IF EXISTS corpus.quran_verse_spans"

# The view as revision 20261004_192000 built it in `app`, for the downgrade.
PREVIOUS_SPAN_STATEMENTS = tuple(
    statement.replace("corpus.", "app.") for statement in VERSE_SPAN_STATEMENTS
)
DROP_PREVIOUS_SPANS = "DROP MATERIALIZED VIEW IF EXISTS app.quran_verse_spans"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.execute(DROP_PREVIOUS_SPANS)
    for table in TABLES:
        op.execute(f"ALTER TABLE {PREVIOUS_SCHEMA}.{table} SET SCHEMA {SCHEMA}")
    for statement in VERSE_SPAN_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(DROP_VERSE_SPANS)
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE {SCHEMA}.{table} SET SCHEMA {PREVIOUS_SCHEMA}")
    for statement in PREVIOUS_SPAN_STATEMENTS:
        op.execute(statement)
