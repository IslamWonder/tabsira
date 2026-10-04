"""
The scripture store: Quran verses and hadiths kept letter by letter as their source gives them.

Displayed text lives in `quran_verses.text` and `hadiths.text`, each with the
SHA-256 of its UTF-8 bytes. The database checks that hash on every row and
refuses any insert, update or delete of scripture unless the transaction set
`tabsira.scripture_write` (see `src/scripture/guard.py`), which only the
importers and the correction sync do.

The search copies (diacritics removed, letters folded) sit in their own tables,
`quran_verse_search` and `hadith_search`, so a query on the display tables can
never pick one up by accident. The annotations and the Sunnah signals are
model-written retrieval aids and are never displayed as scripture.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DDL,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    column,
    event,
    func,
    table,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

SHA256_LENGTH = 64
# The words of a search copy for full-text search: the `simple` configuration
# keeps every word as it is (no stemmer; the copy is folded already).
SEARCH_VECTOR = "to_tsvector('simple'::regconfig, normalized_text)"
# The text column and its hash agree, or the row does not exist.
HASH_MATCHES_TEXT = "text_sha256 = encode(sha256(convert_to(text, 'UTF8')), 'hex')"
# How many words a guard skeleton has, kept by the database beside it (written as
# PostgreSQL prints it back, so the migration check sees no difference).
GUARD_WORDS_SQL = "cardinality(string_to_array(guard_text, ' '::text))"


class HadithClassification(StrEnum):
    """An editor's reading of a dorar.net ruling; only the first two make a hadith evidence."""

    SAHIH = "صحيح"
    HASAN = "حسن"
    DAIF = "ضعيف"
    MAWDU = "موضوع"
    DISPUTED = "مختلف_فيه"


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _identity_pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


class QuranSurah(Base):
    """One surah of quranpedia's mushaf 2, with the facts the insight pages show."""

    __tablename__ = "quran_surahs"

    number: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    # As the mushaf names it, e.g. «سورة الفاتحة».
    name_ar: Mapped[str] = mapped_column(Text)
    # «مكية» or «مدنية», as quranpedia's surah information gives it.
    revelation_place: Mapped[str] = mapped_column(Text)
    revelation_order: Mapped[int] = mapped_column(SmallInteger)
    # Verses of this surah in the mushaf (the Kufan count of Hafs).
    ayah_count: Mapped[int] = mapped_column(SmallInteger)
    words_count: Mapped[int] = mapped_column(Integer)
    source_version: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = _now()


class QuranVerse(Base):
    """A verse of «مصحف حفص نسخة نصية» (quranpedia mushaf 2), its text exactly as the dump gives it."""

    __tablename__ = "quran_verses"
    __table_args__ = (
        UniqueConstraint("surah", "ayah", name="uq_quran_verses_surah_ayah"),
        CheckConstraint(HASH_MATCHES_TEXT, name="text_hash"),
        CheckConstraint("text <> ''", name="text_not_empty"),
        CheckConstraint("ayah >= 1", name="ayah_positive"),
    )

    id: Mapped[int] = _identity_pk()
    surah: Mapped[int] = mapped_column(SmallInteger, ForeignKey("quran_surahs.number"))
    ayah: Mapped[int] = mapped_column(SmallInteger)
    quranpedia_ayah_id: Mapped[int] = mapped_column(Integer, unique=True)
    mushaf_id: Mapped[int] = mapped_column(SmallInteger)
    page: Mapped[int] = mapped_column(SmallInteger)
    juz: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    # Where this exact text came from: `dump:<version>` or `change:<changed_at>`.
    source_version: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = _now()


class QuranVerseHistory(Base):
    """A text a verse carried before a correction replaced it; never edited, never removed."""

    __tablename__ = "quran_verse_history"
    __table_args__ = (
        CheckConstraint(HASH_MATCHES_TEXT, name="text_hash"),
        Index("ix_quran_verse_history_verse_id", "verse_id"),
    )

    id: Mapped[int] = _identity_pk()
    verse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("quran_verses.id"))
    surah: Mapped[int] = mapped_column(SmallInteger)
    ayah: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    source_version: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    replaced_by_version: Mapped[str] = mapped_column(Text)
    replaced_at: Mapped[datetime] = _now()


class QuranVerseSearch(Base):
    """The search copy of a verse: folded for matching, never shown."""

    __tablename__ = "quran_verse_search"
    __table_args__ = (
        Index(
            "ix_quran_verse_search_normalized_text_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
        Index(
            "ix_quran_verse_search_guard_text_trgm",
            "guard_text",
            postgresql_using="gin",
            postgresql_ops={"guard_text": "gin_trgm_ops"},
        ),
        Index("ix_quran_verse_search_guard_words", "guard_words"),
        Index("ix_quran_verse_search_search_vector", "search_vector", postgresql_using="gin"),
    )

    verse_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quran_verses.id", ondelete="CASCADE"), primary_key=True
    )
    normalized_text: Mapped[str] = mapped_column(Text)
    # The leak guard's skeleton of the text (`src.scripture.guard_fold`), for no other use.
    guard_text: Mapped[str] = mapped_column(Text)
    # The words of the skeleton, counted by the database: the leak guard reads the verses
    # of a few words through its index (`src.scripture.overlap`).
    guard_words: Mapped[int] = mapped_column(Integer, Computed(GUARD_WORDS_SQL, persisted=True))
    # Computed by the database from the copy, so no importer has to keep it.
    search_vector: Mapped[str] = mapped_column(TSVECTOR, Computed(SEARCH_VECTOR, persisted=True))


# The guard skeleton of each verse followed by the next six words of its surah,
# whatever the verses they come from: a run of seven words that crosses from one
# verse to the next (short verses quoted one after another) lies whole in one span.
# A materialized view of the search copies, rebuilt by the importer and the
# correction sync (`refresh_verse_spans`), never shown. The migration that creates
# it writes the same statements out; a test keeps the two identical.
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

quran_verse_spans = table(
    "quran_verse_spans",
    column("verse_id", BigInteger),
    column("guard_text", Text),
    schema="app",
)

for _statement in VERSE_SPAN_STATEMENTS:
    # SQLAlchemy ships DDL without type hints.
    _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
    event.listen(QuranVerseSearch.__table__, "after_create", _ddl.execute_if(dialect="postgresql"))
event.listen(
    QuranVerseSearch.__table__,
    "before_drop",
    DDL(DROP_VERSE_SPANS).execute_if(dialect="postgresql"),  # type: ignore[no-untyped-call]
)


class QuranAnnotation(Base):
    """
    The model-written annotation of a verse from the annotated corpus, for retrieval only.

    Joined to the verse by surah and ayah. The corpus' own verse text is never
    stored: the displayed text is always `quran_verses.text`.
    """

    __tablename__ = "quran_annotations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["surah", "ayah"],
            ["quran_verses.surah", "quran_verses.ayah"],
            name="fk_quran_annotations_surah_ayah_quran_verses",
        ),
    )

    surah: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ayah: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    source_ayah_id: Mapped[int] = mapped_column(Integer)
    islamic_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text))
    key_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text))
    keywords_ar: Mapped[list[str]] = mapped_column(ARRAY(Text))
    semantic_tags: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # The seven whitelisted annotation keys, as the corpus has them.
    annotation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    annotation_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    imported_at: Mapped[datetime] = _now()


class HadithCollection(Base):
    """One of the nine books, with the dataset, licence and version its text came from."""

    __tablename__ = "hadith_collections"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_ar: Mapped[str] = mapped_column(Text)
    source_dataset: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    licence: Mapped[str] = mapped_column(Text)
    # The commit of the dataset the file was taken from.
    source_version: Mapped[str] = mapped_column(Text)
    source_file: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    display_order: Mapped[int] = mapped_column(SmallInteger)
    imported_at: Mapped[datetime] = _now()


class Hadith(Base):
    """A hadith exactly as its dataset gives it: number, text (with any RTL marks), grades."""

    __tablename__ = "hadiths"
    __table_args__ = (
        UniqueConstraint("collection", "number", name="uq_hadiths_collection_number"),
        CheckConstraint(HASH_MATCHES_TEXT, name="text_hash"),
        CheckConstraint("text <> ''", name="text_not_empty"),
    )

    id: Mapped[int] = _identity_pk()
    collection: Mapped[str] = mapped_column(String(32), ForeignKey("hadith_collections.slug"))
    # The dataset's own number, kept as text: «402.2» is not the float 402.2.
    number: Mapped[str] = mapped_column(String(32))
    # fawazahmed0's second numbering (Abd al-Baqi's for Muslim), when there is one.
    arabic_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    book_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    book_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    number_in_book: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    # The dataset's grades, as given. Informational only: eligibility comes from
    # an editor's dorar.net ruling (`hadith_rulings`), never from these.
    informational_grades: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)
    source_dataset: Mapped[str] = mapped_column(Text)
    source_version: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = _now()


class HadithSearch(Base):
    """The search copy of a hadith: folded for matching, never shown."""

    __tablename__ = "hadith_search"
    __table_args__ = (
        Index(
            "ix_hadith_search_normalized_text_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
        Index(
            "ix_hadith_search_guard_text_trgm",
            "guard_text",
            postgresql_using="gin",
            postgresql_ops={"guard_text": "gin_trgm_ops"},
        ),
        Index("ix_hadith_search_search_vector", "search_vector", postgresql_using="gin"),
    )

    hadith_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hadiths.id", ondelete="CASCADE"), primary_key=True
    )
    normalized_text: Mapped[str] = mapped_column(Text)
    # The leak guard's skeleton of the text (`src.scripture.guard_fold`), for no other use.
    guard_text: Mapped[str] = mapped_column(Text)
    # Computed by the database from the copy, so no importer has to keep it.
    search_vector: Mapped[str] = mapped_column(TSVECTOR, Computed(SEARCH_VECTOR, persisted=True))


class HadithSignal(Base):
    """
    Ranking signals of one record of the enriched Sunnah file, linked to a hadith by text match.

    Every field here was written by a language model. `model_written_summary`
    and `model_written_rephrase` paraphrase a hadith: they are never shown as
    hadith text, never quoted, and never returned by the scripture API.
    """

    __tablename__ = "hadith_signals"
    __table_args__ = (Index("ix_hadith_signals_hadith_id", "hadith_id"),)

    id: Mapped[int] = _identity_pk()
    source_record_id: Mapped[str] = mapped_column(String(16), unique=True)
    hadith_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hadiths.id"), nullable=True
    )
    match_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Every hadith that matched above the threshold, best first: [{hadith_id, coverage}].
    matches: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_old: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_new: Mapped[str | None] = mapped_column(Text, nullable=True)
    subcategory: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_tags: Mapped[list[str]] = mapped_column(ARRAY(Text))
    key_concepts: Mapped[list[str]] = mapped_column(ARRAY(Text))
    topics_for_retrieval: Mapped[list[str]] = mapped_column(ARRAY(Text))
    sciences: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model_written_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_written_rephrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by_model: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    imported_at: Mapped[datetime] = _now()


class HadithRuling(Base):
    """
    A dorar.net ruling an editor recorded by hand (decision 18); append-only.

    The ruling text is copied verbatim from dorar; the classification is the
    editor's reading of it. The latest ruling of a hadith is the one in force.
    """

    __tablename__ = "hadith_rulings"
    __table_args__ = (
        Index("ix_hadith_rulings_hadith_id_recorded_at", "hadith_id", "recorded_at"),
        CheckConstraint(r"dorar_url ~ '^https://(www\.)?dorar\.net/'", name="dorar_url"),
        CheckConstraint("ruling_text <> ''", name="ruling_text_not_empty"),
        CheckConstraint("editor_name <> ''", name="editor_name_not_empty"),
    )

    id: Mapped[int] = _identity_pk()
    hadith_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hadiths.id"))
    ruling_text: Mapped[str] = mapped_column(Text)
    scholar: Mapped[str] = mapped_column(Text)
    source_book: Mapped[str] = mapped_column(Text)
    page: Mapped[str] = mapped_column(Text)
    dorar_url: Mapped[str] = mapped_column(Text)
    classification: Mapped[HadithClassification] = mapped_column(
        Enum(
            HadithClassification,
            name="classification",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            length=32,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    # The editor's account once accounts exist; until then the name below.
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    editor_name: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = _now()


class HadithVerificationQueue(Base):
    """A hadith the pipeline wanted but that has no ruling yet, ordered by demand."""

    __tablename__ = "hadith_verification_queue"
    __table_args__ = (Index("ix_hadith_verification_queue_demand_count", "demand_count"),)

    hadith_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hadiths.id", ondelete="CASCADE"), primary_key=True
    )
    demand_count: Mapped[int] = mapped_column(Integer)
    first_requested_at: Mapped[datetime] = _now()
    last_requested_at: Mapped[datetime] = _now()


class ScriptureAudit(Base):
    """One write to the scripture store: an import run or a corrected text; append-only."""

    __tablename__ = "scripture_audit"
    __table_args__ = (Index("ix_scripture_audit_entity_key", "entity", "entity_key"),)

    id: Mapped[int] = _identity_pk()
    # What was written: `quran_verse`, `hadith`, `quran_import`, `hadith_import`.
    entity: Mapped[str] = mapped_column(String(32))
    # Which one: `30:50`, `bukhari:1032`, a dump or file name.
    entity_key: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(32))
    old_sha256: Mapped[str | None] = mapped_column(String(SHA256_LENGTH), nullable=True)
    new_sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH))
    # Where the new text came from: a dump URL and version, or a refetch path.
    source: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = _now()


class ScriptureSyncState(Base):
    """How far a correction feed has been applied; read and written by the sync job only."""

    __tablename__ = "scripture_sync_state"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    # The next run asks the feed for everything changed since this date.
    synced_through: Mapped[date] = mapped_column(Date)
    dump_version: Mapped[str] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


# The guard and its triggers, written out again in the migration that creates
# the tables; these copies build them when a test schema is created from the models.
GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION app.scripture_write_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF coalesce(current_setting('tabsira.scripture_write', true), '') IN ('import', 'sync') THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION '% on %.% refused: scripture is written only by its importers and the sync job',
        TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END
$$
"""

# Scripture tables refuse every write; the append-only ones refuse changes and removals.
GUARDED_TABLES = {
    "quran_verses": "INSERT OR UPDATE OR DELETE",
    "quran_verse_history": "INSERT OR UPDATE OR DELETE",
    "hadiths": "INSERT OR UPDATE OR DELETE",
    "hadith_rulings": "UPDATE OR DELETE",
    "scripture_audit": "UPDATE OR DELETE",
}


def guard_trigger_statements(table: str, events: str) -> tuple[str, str]:
    """Return the row trigger and the TRUNCATE trigger that guard `table`."""
    row = (
        f"CREATE TRIGGER {table}_write_guard BEFORE {events} ON app.{table} "
        "FOR EACH ROW EXECUTE FUNCTION app.scripture_write_guard()"
    )
    truncate = (
        f"CREATE TRIGGER {table}_truncate_guard BEFORE TRUNCATE ON app.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION app.scripture_write_guard()"
    )
    return row, truncate


# SQLAlchemy ships DDL without type hints. DDL formats its statement with %,
# so the placeholders of the RAISE message are doubled here.
_function = DDL(GUARD_FUNCTION.replace("%", "%%"))  # type: ignore[no-untyped-call]
event.listen(Base.metadata, "before_create", _function.execute_if(dialect="postgresql"))
for _table, _events in GUARDED_TABLES.items():
    for _statement in guard_trigger_statements(_table, _events):
        _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
        event.listen(
            Base.metadata.tables[f"app.{_table}"],
            "after_create",
            _ddl.execute_if(dialect="postgresql"),
        )
