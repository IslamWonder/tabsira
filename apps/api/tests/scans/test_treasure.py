"""The hidden treasure's rules: verified candidates only, shown on return only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.models import HadithClassification, TreasureKind
from src.pipeline.engine import HadithRef, QuranRef
from src.services import treasure
from src.services.treasure import Candidate, UnitInfo, candidates, parse_anchor, treasure_ready
from tests.scans.conftest import rule

PATH = "tabsira-masar-1.0"
T0 = datetime(2026, 10, 4, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        ("Q:30:50", QuranRef(surah=30, ayah=50)),
        ("H:bukhari:2320", HadithRef(collection="bukhari", number="2320")),
        ("H:muslim:35b", HadithRef(collection="muslim", number="35b")),
        ("Q:3:190-191", None),
        ("Q:115:1", None),
        ("Q:2:300", None),
        ("قاعدة الفصل بين الرصد والتفسير", None),
    ],
)
def test_an_anchor_is_one_whole_text_or_nothing(anchor, expected):
    assert parse_anchor(anchor) == expected


def unit(identifier: str, domain: str, position: int, prerequisites=(), anchors=()) -> UnitInfo:
    return UnitInfo(identifier, domain, position, tuple(prerequisites), tuple(anchors))


def test_candidates_are_the_unit_texts_then_the_units_that_build_on_it():
    base = unit("T01_01", "T01", 1, anchors=("Q:3:190-191", "Q:3:191"))
    units = [
        base,
        unit("T01_04", "T01", 4, ["T01_01"], ["Q:16:18"]),
        unit("T01_03", "T01", 3, ["T01_01"], ["Q:6:99", "H:bukhari:2320"]),
        unit("T02_01", "T02", 1, ["T01_01"], ["Q:2:21"]),
        unit("T01_05", "T01", 5, ["T01_04"], ["Q:14:7"]),
    ]

    assert candidates(base, units) == [
        Candidate(TreasureKind.ALTERNATIVE, QuranRef(surah=3, ayah=191), "T01_01"),
        Candidate(TreasureKind.DEEPER, QuranRef(surah=6, ayah=99), "T01_03"),
        Candidate(TreasureKind.DEEPER, HadithRef(collection="bukhari", number="2320"), "T01_03"),
        Candidate(TreasureKind.DEEPER, QuranRef(surah=16, ayah=18), "T01_04"),
    ]


@pytest.mark.parametrize(
    ("values", "ready"),
    [
        ({}, False),
        ({"now": T0 + timedelta(days=3)}, True),
        ({"last_visit": T0 + timedelta(hours=1)}, False),
        ({"last_visit": T0 + timedelta(hours=12)}, True),
        ({"related_completed_after": True}, True),
    ],
)
def test_a_treasure_shows_only_on_return(values, ready):
    arguments = {
        "now": T0 + timedelta(hours=2),
        "last_visit": None,
        "related_completed_after": False,
        "reveal_after": timedelta(days=3),
        "return_after": timedelta(hours=12),
    } | values

    assert treasure_ready(T0, **arguments) is ready


async def test_the_first_verified_candidate_not_already_met_is_chosen(store):
    async with store() as db:
        await rule(db, "bukhari", "2320")
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)

        deeper = await treasure.choose(db, unit_id="T01_01", path_version=PATH, excluded=[])
        skipped = await treasure.choose(
            db, unit_id="T01_01", path_version=PATH, excluded=[QuranRef(surah=6, ayah=99)]
        )
        alternative = await treasure.choose(
            db, unit_id="T12_02", path_version=PATH, excluded=[QuranRef(surah=6, ayah=99)]
        )
        nothing = await treasure.choose(
            db, unit_id="T01_06", path_version=PATH, excluded=[QuranRef(surah=30, ayah=50)]
        )
        unknown = await treasure.choose(db, unit_id="T99_99", path_version=PATH, excluded=[])

        assert await treasure.verified(db, HadithRef(collection="bukhari", number="2320"))
        assert not await treasure.verified(db, HadithRef(collection="bukhari", number="1032"))
        # Decision 64: a hadith with no ruling is shown, so it is verified.
        assert await treasure.verified(db, HadithRef(collection="bukhari", number="8"))
        assert not await treasure.verified(db, HadithRef(collection="bukhari", number="999999"))
        assert not await treasure.verified(db, QuranRef(surah=114, ayah=1))

    assert deeper == Candidate(TreasureKind.DEEPER, QuranRef(surah=6, ayah=99), "T01_03")
    # 16:10-11 is a range and 16:18 is not in the test store: nothing else is verified.
    assert skipped is None
    assert alternative == Candidate(
        TreasureKind.ALTERNATIVE, HadithRef(collection="bukhari", number="2320"), "T12_02"
    )
    assert nothing is None
    assert unknown is None


async def test_a_hadith_with_no_ruling_is_a_verified_candidate_until_ruled_out(store):
    async with store() as db:
        await rule(db, "bukhari", "8", HadithClassification.DAIF)

        # Decision 64: no ruling is enough; a ruling of ضعيف keeps it out.
        assert await treasure.verified(db, HadithRef(collection="bukhari", number="2320"))
        assert not await treasure.verified(db, HadithRef(collection="bukhari", number="8"))
