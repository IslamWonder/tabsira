"""The scripture tables: the hash the database checks, the write guard and the search copy."""

from __future__ import annotations

import hashlib
import importlib.util
import unicodedata
from pathlib import Path

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from src.models import (
    HadithClassification,
    HadithCollection,
    HadithRuling,
    QuranSurah,
    QuranVerse,
    ScriptureAudit,
)
from src.models import scripture as scripture_models
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.text import search_copy, sha256_hex
from tests.scripture_fixtures import hadith_text, load_json, verse_text

API_DIR = Path(__file__).resolve().parents[1]
# Alif forms, alif maqsura, teh marbuta, hamza seats, tatweel, RLM, quotes and Arabic comma.
FOLDED_AWAY = (
    0x0623,
    0x0625,
    0x0622,
    0x0671,
    0x0649,
    0x0629,
    0x0624,
    0x0626,
    0x0640,
    0x200F,
    0x22,
    0x060C,
)


def _surah() -> QuranSurah:
    return QuranSurah(
        number=30,
        name_ar="x",
        revelation_place="x",
        revelation_order=84,
        ayah_count=60,
        words_count=817,
        source_version="dump:test",
    )


def _verse(body: str, *, digest: str | None = None) -> QuranVerse:
    return QuranVerse(
        surah=30,
        ayah=50,
        quranpedia_ayah_id=65709,
        mushaf_id=2,
        page=409,
        juz=21,
        text=body,
        text_sha256=digest or sha256_hex(body),
        source_version="dump:test",
    )


async def _store_verse(session, *, purpose: WritePurpose = WritePurpose.IMPORT) -> QuranVerse:
    session.add(_surah())
    await session.flush()
    async with session.begin_nested():
        await allow_scripture_writes(session, purpose)
        verse = _verse(verse_text(30, 50))
        session.add(verse)
        await session.flush()
    return verse


async def _close_guard(session) -> None:
    await session.execute(text("SELECT set_config('tabsira.scripture_write', '', true)"))


def test_the_hash_is_the_sha256_of_the_utf8_bytes():
    body = verse_text(30, 50)

    assert sha256_hex(body) == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert len(sha256_hex(body)) == 64


def test_the_search_copy_folds_two_encodings_of_one_verse_to_the_same_key():
    quranpedia = verse_text(30, 50)
    king_fahd_v13 = load_json("kfgqpc-v13-30-50.json")["text"]

    assert quranpedia != king_fahd_v13
    assert search_copy(quranpedia) == search_copy(king_fahd_v13)


def test_the_search_copy_keeps_letters_only_and_never_equals_the_display_text():
    for body in (verse_text(1, 1), verse_text(30, 50), hadith_text("bukhari", 1032)):
        folded = search_copy(body)

        assert folded != body
        assert folded == folded.strip()
        assert "  " not in folded
        assert not any(unicodedata.category(char) == "Mn" for char in folded)
        assert not set(folded) & {chr(code) for code in FOLDED_AWAY}
        assert search_copy(folded) == folded


def test_the_search_copy_spells_out_the_honorific_and_folds_the_uthmani_madda():
    assert search_copy("قال ﷺ") == "قال صلي الله عليه وسلم"
    assert search_copy("ءامن") == search_copy("آمن") == "امن"


async def test_a_verse_is_stored_only_while_the_guard_is_open(db_session):
    db_session.add(_surah())
    await db_session.flush()

    with pytest.raises(IntegrityError, match="scripture is written only by"):
        async with db_session.begin_nested():
            db_session.add(_verse(verse_text(30, 50)))
            await db_session.flush()

    verse = await _store_verse_after_surah(db_session)
    stored = await db_session.scalar(select(QuranVerse.text).where(QuranVerse.id == verse.id))
    assert stored == verse_text(30, 50)
    assert sha256_hex(stored) == verse.text_sha256


async def _store_verse_after_surah(session) -> QuranVerse:
    async with session.begin_nested():
        await allow_scripture_writes(session, WritePurpose.SYNC)
        verse = _verse(verse_text(30, 50))
        session.add(verse)
        await session.flush()
    return verse


async def test_an_ordinary_update_delete_or_truncate_of_a_verse_is_refused(db_session):
    verse = await _store_verse(db_session)
    await _close_guard(db_session)

    statements = (
        update(QuranVerse).where(QuranVerse.id == verse.id).values(page=1),
        text("DELETE FROM app.quran_verses"),
        text("TRUNCATE app.quran_verses CASCADE"),
        text("UPDATE app.quran_verses SET text = text"),
    )
    for statement in statements:
        with pytest.raises(IntegrityError, match="refused"):
            async with db_session.begin_nested():
                await db_session.execute(statement)

    assert await db_session.scalar(select(QuranVerse.page)) == 409


async def test_the_database_refuses_a_hash_that_does_not_match_the_text(db_session):
    db_session.add(_surah())
    await db_session.flush()

    with pytest.raises(IntegrityError, match="ck_quran_verses_text_hash"):
        async with db_session.begin_nested():
            await allow_scripture_writes(db_session, WritePurpose.IMPORT)
            db_session.add(_verse(verse_text(30, 50), digest=sha256_hex(verse_text(1, 1))))
            await db_session.flush()


async def test_the_guard_ends_with_the_transaction(engine):
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(
                text("SELECT set_config('tabsira.scripture_write', 'sync', true)")
            )
            inside = await connection.scalar(
                text("SELECT current_setting('tabsira.scripture_write', true)")
            )
        after = await connection.scalar(
            text("SELECT current_setting('tabsira.scripture_write', true)")
        )

    assert inside == "sync"
    assert after in {None, ""}


async def test_a_ruling_is_appended_freely_but_never_changed_or_removed(db_session):
    db_session.add(
        HadithCollection(
            slug="bukhari",
            name_ar="x",
            source_dataset="x",
            source_url="x",
            licence="x",
            source_version="x",
            source_file="x",
            source_sha256="0" * 64,
            display_order=1,
        )
    )
    await db_session.flush()
    async with db_session.begin_nested():
        await allow_scripture_writes(db_session, WritePurpose.IMPORT)
        hadith_id = await db_session.scalar(
            text(
                "INSERT INTO app.hadiths (collection, number, text, text_sha256, source_dataset,"
                " source_version) VALUES ('bukhari', '1032', :body, :digest, 'x', 'x')"
                " RETURNING id"
            ),
            {
                "body": hadith_text("bukhari", 1032),
                "digest": sha256_hex(hadith_text("bukhari", 1032)),
            },
        )
    await _close_guard(db_session)
    ruling = HadithRuling(
        hadith_id=hadith_id,
        ruling_text="x",
        scholar="x",
        source_book="x",
        page="1",
        dorar_url="https://dorar.net/hadith/sharh/1",
        classification=HadithClassification.SAHIH,
        editor_name="x",
    )
    db_session.add(ruling)
    await db_session.flush()

    for statement in (
        update(HadithRuling).values(ruling_text="y"),
        text("DELETE FROM app.hadith_rulings"),
        text("UPDATE app.hadiths SET number = '1'"),
    ):
        with pytest.raises(IntegrityError, match="refused"):
            async with db_session.begin_nested():
                await db_session.execute(statement)

    with pytest.raises(IntegrityError, match="ck_hadith_rulings_dorar_url"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO app.hadith_rulings (hadith_id, ruling_text, scholar, source_book,"
                    " page, dorar_url, classification, editor_name) VALUES"
                    " (:id, 'x', 'x', 'x', '1', 'https://example.org/', 'حسن', 'x')"
                ),
                {"id": hadith_id},
            )


async def test_the_audit_log_is_append_only(db_session):
    db_session.add(
        ScriptureAudit(
            entity="quran_verse",
            entity_key="30:50",
            action="correct",
            new_sha256="0" * 64,
            source="test",
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError, match="refused"):
        async with db_session.begin_nested():
            await db_session.execute(update(ScriptureAudit).values(source="other"))


def test_the_migration_creates_the_same_guard_as_the_models():
    path = next((API_DIR / "alembic" / "versions").glob("*_create_scripture_tables.py"))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.GUARD_FUNCTION == scripture_models.GUARD_FUNCTION
    assert migration.GUARDED_TABLES == scripture_models.GUARDED_TABLES


async def test_every_guarded_table_has_its_two_triggers(db_session):
    triggers = set(
        (
            await db_session.execute(
                text(
                    "SELECT tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'app' AND NOT t.tgisinternal"
                )
            )
        ).scalars()
    )

    for table in scripture_models.GUARDED_TABLES:
        assert {f"{table}_write_guard", f"{table}_truncate_guard"} <= triggers
