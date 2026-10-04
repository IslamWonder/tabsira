"""dorar.net rulings recorded by editors: eligibility, the queue, the links and the command."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from src.cli import record_ruling as ruling_command
from src.models import Hadith, HadithClassification, HadithRuling, HadithVerificationQueue
from src.scripture.links import distinctive_words, dorar_search_url, quranpedia_verse_url
from src.scripture.rulings import (
    RulingError,
    RulingInput,
    enqueue_demand,
    find_hadith,
    is_eligible,
    latest_ruling,
    record_ruling,
    verification_queue,
)
from src.scripture.spans import SpanRole, hadith_spans
from src.scripture.text import search_copy
from tests.scripture.fixtures import hadith_text, store_hadiths

DORAR_PAGE = "https://dorar.net/h/abc123"


def _ruling(classification: HadithClassification, **changes) -> RulingInput:
    values = {
        "ruling_text": " [صحيح] ",
        "scholar": "x",
        "source_book": "x",
        "page": "12",
        "dorar_url": DORAR_PAGE,
        "classification": classification,
        "editor_name": "editor",
        **changes,
    }
    return RulingInput(**values)


async def _hadith(session, collection: str = "bukhari", number: str = "1032") -> Hadith:
    found = await find_hadith(session, collection, number)
    assert found is not None
    return found


async def test_only_a_latest_ruling_of_sahih_or_hasan_makes_a_hadith_eligible(hadith_session):
    hadith = await _hadith(hadith_session)
    seen = [await is_eligible(hadith_session, hadith.id)]

    for classification in (
        HadithClassification.SAHIH,
        HadithClassification.DAIF,
        HadithClassification.HASAN,
        HadithClassification.MAWDU,
        HadithClassification.DISPUTED,
    ):
        await record_ruling(hadith_session, hadith.id, _ruling(classification))
        seen.append(await is_eligible(hadith_session, hadith.id))

    assert seen == [False, True, False, True, False, False]
    history = (await hadith_session.scalars(select(HadithRuling))).all()
    assert len(history) == 5
    latest = await latest_ruling(hadith_session, hadith.id)
    assert latest is not None
    assert latest.classification is HadithClassification.DISPUTED


async def test_a_ruling_is_kept_exactly_as_typed(hadith_session):
    hadith = await _hadith(hadith_session)

    row = await record_ruling(hadith_session, hadith.id, _ruling(HadithClassification.HASAN))

    assert row.ruling_text == " [صحيح] "
    assert (row.editor_name, row.recorded_by, row.dorar_url) == ("editor", None, DORAR_PAGE)


async def test_demand_is_counted_until_a_ruling_takes_the_hadith_off_the_queue(hadith_session):
    wanted = await _hadith(hadith_session)
    other = await _hadith(hadith_session, "muslim", "113")

    assert await enqueue_demand(hadith_session, wanted.id)
    assert await enqueue_demand(hadith_session, wanted.id)
    assert await enqueue_demand(hadith_session, other.id)
    queue = await verification_queue(hadith_session)
    assert [(item.hadith.id, item.demand_count) for item in queue] == [
        (wanted.id, 2),
        (other.id, 1),
    ]
    assert queue[0].first_requested_at <= queue[0].last_requested_at

    await record_ruling(hadith_session, wanted.id, _ruling(HadithClassification.SAHIH))

    assert not await enqueue_demand(hadith_session, wanted.id)
    left = (await hadith_session.scalars(select(HadithVerificationQueue.hadith_id))).all()
    assert left == [other.id]


async def test_a_ruling_for_no_stored_hadith_is_refused(db_session):
    with pytest.raises(RulingError, match="no stored hadith has id 999999"):
        await record_ruling(db_session, 999_999, _ruling(HadithClassification.SAHIH))


@pytest.mark.parametrize(
    "changes",
    [
        {"ruling_text": "  "},
        {"editor_name": ""},
        {"dorar_url": "http://dorar.net/h/abc"},
        {"dorar_url": "https://dorar.net.example.org/h/abc"},
        {"dorar_url": "https://dorar.net/"},
        {"classification": "قوي"},
    ],
)
def test_a_ruling_that_is_blank_off_dorar_or_unclassified_is_refused(changes):
    with pytest.raises(ValidationError):
        _ruling(**{"classification": HadithClassification.SAHIH, **changes})


def test_the_dorar_page_may_be_on_either_host():
    assert _ruling(HadithClassification.SAHIH, dorar_url="https://www.dorar.net/h/x").dorar_url


def test_a_verse_links_to_its_quranpedia_page_in_mushaf_2():
    assert quranpedia_verse_url(30, 65709) == "https://quranpedia.net/surah/2/30#verse-65709"


def test_the_dorar_link_searches_the_prophets_words_with_every_word_required():
    text = hadith_text("bukhari", 1032)
    spans = {span.role: span for span in hadith_spans(text)}
    words_span = spans[SpanRole.WORDS]

    url = urlsplit(dorar_search_url(text))
    query = parse_qs(url.query)

    assert (url.scheme, url.netloc, url.path) == ("https", "dorar.net", "/hadith/search")
    assert query["st"] == ["w"]
    words = query["q"][0].split()
    assert words == distinctive_words(text)
    assert 0 < len(words) <= 7
    for word in words:
        assert search_copy(word) in search_copy(text[words_span.start : words_span.end])


def test_without_quoted_words_the_link_uses_the_body_or_the_middle():
    chained = "حَدَّثَنَا فُلَانٍ عَنْ فُلَانٍ أَنَّ رَسُولَ اللَّهِ قَالَ خَيْرٌ كَثِيرٌ"
    unsure = "خَيْرٌ كَثِيرٌ وَفَضْلٌ عَظِيمٌ"

    assert distinctive_words(chained) == ["خير", "كثير"]
    assert distinctive_words(unsure) == ["وفضل", "عظيم"]


async def test_the_command_lists_the_queue_and_records_a_ruling(scripture_maker, tmp_path, capsys):
    async with scripture_maker() as session, session.begin():
        await store_hadiths(session)
    async with scripture_maker() as session, session.begin():
        await enqueue_demand(session, (await _hadith(session)).id)
    ruling_file = tmp_path / "ruling.txt"
    ruling_file.write_text(" [إسناده صحيح] \n", encoding="utf-8")
    record = [
        "record",
        "bukhari",
        "1032",
        "--ruling-file",
        str(ruling_file),
        "--scholar",
        "s",
        "--book",
        "b",
        "--page",
        "3",
        "--url",
        DORAR_PAGE,
        "--classification",
        "صحيح",
        "--editor",
        "e",
    ]

    listed = await ruling_command.run(["queue"], sessionmaker=scripture_maker)
    recorded = await ruling_command.run(record, sessionmaker=scripture_maker)
    weak = await ruling_command.run(
        [
            *record[:3],
            "--ruling",
            "ضعيف",
            *record[5:-4],
            "--classification",
            "ضعيف",
            "--editor",
            "e",
        ],
        sessionmaker=scripture_maker,
    )
    empty = await ruling_command.run(["queue", "--limit", "5"], sessionmaker=scripture_maker)

    out = capsys.readouterr().out
    assert (listed, recorded, weak, empty) == (0, 0, 0, 0)
    assert "bukhari 1032\twanted 1 times\thttps://dorar.net/hadith/search?q=" in out
    assert ": صحيح, eligible as evidence." in out
    assert ": ضعيف, not eligible as evidence." in out
    assert "No hadith is waiting for a ruling." in out
    async with scripture_maker() as session:
        texts = (
            await session.scalars(select(HadithRuling.ruling_text).order_by(HadithRuling.id))
        ).all()
    assert texts == [" [إسناده صحيح] ", "ضعيف"]


async def test_the_command_refuses_an_unknown_hadith_or_a_bad_ruling(scripture_maker, capsys):
    async with scripture_maker() as session, session.begin():
        await store_hadiths(session)
    base = ["--ruling", "x", "--scholar", "s", "--book", "b", "--page", "3", "--editor", "e"]

    unknown = await ruling_command.run(
        ["record", "bukhari", "99999", *base, "--url", DORAR_PAGE, "--classification", "حسن"],
        sessionmaker=scripture_maker,
    )
    off_dorar = await ruling_command.run(
        [
            "record",
            "bukhari",
            "8",
            *base,
            "--url",
            "https://example.org/x",
            "--classification",
            "حسن",
        ],
        sessionmaker=scripture_maker,
    )

    err = capsys.readouterr().err
    assert (unknown, off_dorar) == (1, 1)
    assert "no stored hadith bukhari 99999" in err
    assert "ruling refused: check dorar_url" in err


async def test_the_command_uses_the_application_database_when_none_is_given(monkeypatch):
    disposed: list[bool] = []

    async def dispose() -> None:
        disposed.append(True)

    monkeypatch.setattr(ruling_command, "dispose_engine", dispose)

    assert await ruling_command.run(["queue"]) == 0
    assert disposed == [True]


def test_main_runs_the_command(monkeypatch):
    async def fake_run(argv):
        return 5

    monkeypatch.setattr(ruling_command, "run", fake_run)

    assert ruling_command.main(["queue"]) == 5
