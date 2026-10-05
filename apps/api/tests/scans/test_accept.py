"""The server checks the engine's insights again before anything is saved."""

from __future__ import annotations

from sqlalchemy import select

from src.models import HadithClassification, HadithVerificationQueue
from src.scans.accept import accept, insight_texts
from src.scripture.rulings import find_hadith
from tests.scans.builders import LEAF, entity, hadith, proposed, quran, scene
from tests.scans.conftest import rule
from tests.scripture.fixtures import enrich_hadith


async def queued(db) -> list[int]:
    return list((await db.scalars(select(HadithVerificationQueue.hadith_id))).all())


async def test_a_sound_insight_is_kept_with_its_box_and_its_waiting_hadith(store):
    async with store() as db:
        accepted = await accept(db, scene(), [proposed(entity_ids=["e1", "ghost"])])

        assert accepted.refusals == []
        kept = accepted.insights[0]
        assert kept.entity_ids == ["e1"]
        assert kept.anchor == LEAF
        assert kept.hadith is not None
        # The evidence gate counted the demand when it chose the texts; the check never counts again.
        assert await queued(db) == []


async def test_a_hadith_of_the_enriched_file_shows_at_once(store):
    async with store() as db:
        stored = await find_hadith(db, "bukhari", "1032")
        await enrich_hadith(db, stored.id)

        accepted = await accept(db, scene(), [proposed(quran=None)])

        # With no verse, the insight stands on the hadith alone: it is shown now (decision 58).
        assert accepted.refusals == []
        assert accepted.insights[0].hadith is not None


async def test_an_enriched_hadith_ruled_out_is_dropped_like_any_other(store):
    async with store() as db:
        stored = await find_hadith(db, "bukhari", "1032")
        await enrich_hadith(db, stored.id)
        await rule(db, "bukhari", "1032", HadithClassification.MAWDU)

        accepted = await accept(db, scene(), [proposed()])

        # A ruling, once recorded, decides alone (decision 58).
        assert accepted.insights[0].hadith is None
        assert "hadith_ineligible" in accepted.refusals
        assert await queued(db) == []


async def test_a_ruled_hadith_is_kept_and_a_weak_one_is_dropped(store):
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await rule(db, "bukhari", "8", HadithClassification.DAIF)

        sound = await accept(db, scene(), [proposed()])
        weak = await accept(db, scene(), [proposed(hadith=hadith("bukhari", "8"))])

        assert sound.insights[0].hadith is not None
        assert await queued(db) == []
        assert weak.insights[0].hadith is None
        # Its step rested on another hadith than the one cited, and goes with it.
        assert weak.insights[0].small_step is None
        assert weak.refusals == ["hadith_ineligible", "unknown_reference"]


async def test_evidence_the_store_does_not_hold_or_of_the_wrong_kind_is_dropped(store):
    async with store() as db:
        accepted = await accept(
            db,
            scene(),
            [
                proposed(quran=quran(114, 99), hadith=hadith("bukhari", "999999")),
                proposed(quran=hadith(), hadith=quran()),
                proposed(quran=None, hadith=None),
            ],
        )

    assert accepted.insights == []
    assert accepted.refusals == [
        "quran_missing",
        "hadith_missing",
        "no_evidence",
        "quran_kind",
        "hadith_kind",
        "no_evidence",
        "no_evidence",
    ]


async def test_an_insight_whose_words_look_like_scripture_is_refused(store):
    async with store() as db:
        quoted = proposed(glimpse="قال تعالى: «فانظر إلى آثار رحمت الله كيف يحيي الأرض»")
        copied = proposed(
            explanation=[
                proposed()
                .explanation[0]
                .model_copy(update={"text": "يحي الأرض بعد موتها إن ذلك لمحي الموتى"})
            ]
        )
        accepted = await accept(db, scene(), [quoted, copied, proposed()])

    assert accepted.refusals == ["leak", "leak"]
    assert len(accepted.insights) == 1


async def test_a_unit_outside_its_path_version_is_dropped_and_three_insights_at_most(store):
    async with store() as db:
        accepted = await accept(
            db,
            scene(entity("e1", box=None)),
            [
                proposed(learning_unit_id="T99_99"),
                proposed(learning_path_version=None),
                proposed(),
                proposed(),
            ],
        )

    assert [insight.learning_unit_id for insight in accepted.insights] == [None, None, "T01_06"]
    assert accepted.insights[0].learning_path_version is None
    assert accepted.insights[0].anchor is None
    assert accepted.refusals == ["unknown_unit", "unknown_unit"]


def test_every_text_the_engine_wrote_is_looked_at():
    texts = insight_texts(
        proposed(why=proposed().why.model_copy(update={"personalised_because": "اخترت التفكر"}))
    )

    assert set(texts) == {
        "title",
        "glimpse",
        "explanation.0",
        "explanation.1",
        "why.clue.0",
        "why.limit.0",
        "why.concept",
        "why.personalised_because",
        "small_step",
        "quran.matched_on",
        "hadith.matched_on",
        "quran.link",
    }
    bare = insight_texts(proposed(small_step=None, quran=None, hadith=None))
    assert "small_step" not in bare
    assert "quran.matched_on" not in bare
