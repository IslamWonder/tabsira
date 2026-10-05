"""dorar.net rulings recorded by editors: eligibility, the queue, the links and the command."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, select

from src.cli import record_ruling as ruling_command
from src.models import (
    Hadith,
    HadithClassification,
    HadithRuling,
    HadithSignal,
    HadithVerificationQueue,
)
from src.scripture.guard import WritePurpose, allow_scripture_writes
from src.scripture.links import distinctive_words, dorar_search_url, quranpedia_verse_url
from src.scripture.rulings import (
    DORAR_PAGE as DORAR_RULE,
)
from src.scripture.rulings import (
    RulingError,
    RulingInput,
    eligible_given,
    enqueue_demand,
    enriched_among,
    find_hadith,
    is_eligible,
    is_enriched,
    latest_ruling,
    record_ruling,
    verification_queue,
    weak_by_dataset,
)
from src.scripture.spans import SpanRole, hadith_spans
from src.scripture.text import search_copy
from tests.scripture.fixtures import enrich_hadith, hadith_text, store_hadiths

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


async def test_a_hadith_of_the_enriched_file_shows_without_a_ruling_and_is_still_counted(
    hadith_session,
):
    # Decision 58: no ruling, and a strong link from a record of the file: it shows now, and
    # still counts as demand so editors rule the most shown first.
    hadith = await _hadith(hadith_session)
    other = await _hadith(hadith_session, "muslim", "113")
    await enrich_hadith(hadith_session, hadith.id)

    assert await is_enriched(hadith_session, hadith.id) is True
    assert await is_enriched(hadith_session, other.id) is False
    assert await is_eligible(hadith_session, hadith.id) is True
    assert await is_eligible(hadith_session, other.id) is False
    assert await enqueue_demand(hadith_session, hadith.id) is True
    queued = (await hadith_session.scalars(select(HadithVerificationQueue))).all()
    assert [(row.hadith_id, row.demand_count) for row in queued] == [(hadith.id, 1)]


@pytest.mark.parametrize(
    ("classification", "eligible"),
    [
        (HadithClassification.SAHIH, True),
        (HadithClassification.HASAN, True),
        (HadithClassification.DAIF, False),
        (HadithClassification.MAWDU, False),
        (HadithClassification.DISPUTED, False),
    ],
)
async def test_once_ruled_an_enriched_hadith_follows_its_ruling_alone(
    hadith_session, classification, eligible
):
    hadith = await _hadith(hadith_session)
    await enrich_hadith(hadith_session, hadith.id)

    await record_ruling(hadith_session, hadith.id, _ruling(classification))

    assert await is_eligible(hadith_session, hadith.id) is eligible
    # A ruled hadith is no longer counted: it waits for nothing.
    assert await enqueue_demand(hadith_session, hadith.id) is False


@pytest.mark.parametrize(
    ("coverage", "cited"),
    [(0.79, True), (1.0, False)],
    ids=["a weak link", "a book the record does not cite"],
)
async def test_only_a_strong_link_into_a_cited_book_counts(hadith_session, coverage, cited):
    hadith = await _hadith(hadith_session)
    await enrich_hadith(hadith_session, hadith.id, coverage=coverage, cited=cited)

    assert await is_enriched(hadith_session, hadith.id) is False
    assert await is_eligible(hadith_session, hadith.id) is False


async def test_a_link_counts_only_from_a_records_best_match(hadith_session):
    linked = await _hadith(hadith_session)
    second = await _hadith(hadith_session, "muslim", "113")
    hadith_session.add(
        HadithSignal(
            source_record_id="r9",
            hadith_id=linked.id,
            match_coverage=1.0,
            matches=[
                {"hadith_id": linked.id, "coverage": 1.0, "cited": True},
                {"hadith_id": second.id, "coverage": 0.95, "cited": True},
            ],
            semantic_tags=[],
            key_concepts=[],
            topics_for_retrieval=[],
            sciences={},
            generated_by_model="test",
            source_sha256="0" * 64,
        )
    )
    await hadith_session.flush()

    assert await enriched_among(hadith_session, [linked.id, second.id]) == {linked.id}


async def test_a_hadith_a_dataset_grader_calls_weak_waits_for_an_editor(hadith_session):
    hadith = await _hadith(hadith_session)
    await enrich_hadith(hadith_session, hadith.id)
    # The grade only, never the text: what a dataset grader said of this narration.
    await allow_scripture_writes(hadith_session, WritePurpose.IMPORT)
    hadith.informational_grades = [
        {"name": "Al-Albani", "grade": "Hasan Sahih"},
        {"name": "Zubair Ali Zai", "grade": "Isnaad Daif"},
    ]
    await hadith_session.flush()

    assert await is_enriched(hadith_session, hadith.id) is False
    assert await is_eligible(hadith_session, hadith.id) is False


def test_the_weak_grades_of_the_datasets_are_recognised_in_every_spelling():
    for grade in (
        "Daif",
        "Very Daif",
        "Daif Isnaad",
        "Sanad Daif",
        "Mauquf Daif",
        "Munkar",
        "Mawdu",
        "Batil",
        "Shadh, Sahih",
        "Isnaad Malool",
        "Mursal",
        "Da'if",
        "Maudu",
        "Matruk",
        "Munqati",
        "Mudtarib",
        "ضعيف جدا",
        "موضوع",
        "منكر",
    ):
        assert weak_by_dataset([{"name": "x", "grade": grade}]), grade
    for grade in ("Sahih", "Hasan Sahih", "Isnaad Hasan", "Mauquf Sahih", "Maqtu Hasan", "-"):
        assert not weak_by_dataset([{"name": "x", "grade": grade}]), grade
    assert not weak_by_dataset(None)
    assert not weak_by_dataset([])


async def test_the_enriched_hadiths_are_found_in_one_query(hadith_session):
    first = await _hadith(hadith_session)
    second = await _hadith(hadith_session, "muslim", "113")
    await enrich_hadith(hadith_session, first.id, "r1")
    await enrich_hadith(hadith_session, first.id, "r2")

    assert await enriched_among(hadith_session, []) == set()
    assert await enriched_among(hadith_session, [first.id, second.id]) == {first.id}


def test_eligibility_from_what_is_already_read():
    sahih = HadithRuling(classification=HadithClassification.SAHIH)
    daif = HadithRuling(classification=HadithClassification.DAIF)

    assert eligible_given(None, enriched=True) is True
    assert eligible_given(None, enriched=False) is False
    assert eligible_given(sahih, enriched=False) is True
    assert eligible_given(daif, enriched=True) is False


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
        # The parser would accept these; the database would not, so they stop here.
        {"dorar_url": "https://DORAR.NET/h/abc"},
        {"dorar_url": "https://dorar.net:443/h/abc"},
        {"dorar_url": "https://editor@dorar.net/h/abc"},
        {"dorar_url": "https://dor\tar.net/h/abc"},
        {"scholar": "a\x00b"},
        {"classification": "قوي"},
    ],
)
def test_a_ruling_that_is_blank_off_dorar_or_unclassified_is_refused(changes):
    with pytest.raises(ValidationError):
        _ruling(**{"classification": HadithClassification.SAHIH, **changes})


def test_the_address_rule_is_the_tables_check_constraint():
    """What the validator lets through, the table stores: the two rules are one."""
    constraint = next(
        c
        for c in HadithRuling.__table__.constraints
        if isinstance(c, CheckConstraint) and str(c.sqltext).startswith("dorar_url ~")
    )
    database_rule = str(constraint.sqltext).split("~ '")[1].rstrip("'")

    assert DORAR_RULE.pattern == f"{database_rule.lstrip('^')}\\S+"


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
    ruling_file.write_bytes(" [إسناده صحيح] \r\nx\n".encode())
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
    assert texts == [" [إسناده صحيح] \r\nx", "ضعيف"]


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
