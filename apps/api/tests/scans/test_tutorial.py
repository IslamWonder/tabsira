"""The rain tutorial: prepared, labelled, read from the store, never waiting on a provider."""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from src.models import HadithClassification, WorldRelation
from src.pipeline.leak_guard import LeakGuard, PatternLeakDetector, ShingleOverlapDetector
from src.scripture.overlap import repeats_store
from src.scripture.rulings import find_hadith
from src.services import tutorial_service
from src.services.content import REGIONS_PATH, Regions, load_regions, load_tutorial
from tests.scans.conftest import DATA, rule
from tests.scripture.fixtures import hadith_text, verse_text

EXTRA = json.loads((DATA / "extra-scripture.json").read_text(encoding="utf-8"))


def stored_verse(surah: int, ayah: int) -> str:
    for row in EXTRA["verses"]:
        if (row["surah"], row["ayah"]) == (surah, ayah):
            return str(row["text"])
    return verse_text(surah, ayah)


async def test_the_rain_scene_is_a_prepared_example_with_its_verses_from_the_store(
    browser, store, model
):
    response = await browser.get("/tutorial/rain")

    body = response.json()
    assert response.status_code == 200
    assert (body["label"], body["status"]) == ("مثال موثّق مُعدّ", "prepared")
    assert body["image"] == {
        "path": "/scene/rain-olive.jpg",
        "width": 768,
        "height": 1344,
        "alt": "نبتة زيتون صغيرة تتلقى قطرات المطر",
    }
    drop, planting = body["insights"]
    async with store() as db:
        stored = {
            number: (await find_hadith(db, "bukhari", str(number))).text for number in (1032, 2320)
        }
    assert (drop["title"], planting["title"]) == ("الحياة في قطرة", "الغرس الذي يتعدّاك")
    for insight, (surah, ayah), number in ((drop, (30, 50), 1032), (planting, (6, 99), 2320)):
        verse = insight["quran"]["verse"]
        assert (verse["surah"], verse["ayah"]) == (surah, ayah)
        assert verse["text"] == stored_verse(surah, ayah)
        assert hashlib.sha256(verse["text"].encode()).hexdigest() == verse["sha256"]
        # Decision 64: no ruling yet, and the hadith is shown byte for byte as stored.
        hadith = insight["hadith"]["hadith"]
        assert hadith["text"] == stored[number]
        assert hashlib.sha256(hadith["text"].encode()).hexdigest() == hadith["sha256"]
        assert insight["hadith_status"] == "shown"
        assert "notice" not in insight
    # The rain step rests on its hadith; planting is a suggestion.
    assert drop["small_step"]["label"] == "من السنة"
    assert planting["small_step"]["label"] == "اقتراح عملي"
    assert drop["anchor"] == {"x": 0.06, "y": 0.525, "width": 0.36, "height": 0.06}
    assert model.calls == []


async def test_a_hadith_an_editor_ruled_out_is_left_out_and_a_sound_one_stays(browser, store):
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await rule(db, "bukhari", "2320", HadithClassification.MAWDU)
        await db.commit()

    drop, planting = (await browser.get("/tutorial/rain")).json()["insights"]

    hadith = drop["hadith"]["hadith"]
    assert hadith["text"] == hadith_text("bukhari", 1032)
    assert hashlib.sha256(hadith["text"].encode()).hexdigest() == hadith["sha256"]
    assert drop["hadith"]["why"]["relation_label"] == "صلة بالفعل"
    assert (drop["pair_complete"], drop["hadith_status"]) == (True, "shown")
    assert drop["small_step"]["label"] == "من السنة"
    assert (planting["hadith"], planting["hadith_status"]) == (None, "none")


async def test_a_store_without_the_verses_says_the_asset_is_missing(browser, maker):
    response = await browser.get("/tutorial/rain")

    assert (response.status_code, response.json()["error"]) == (503, "ASSET_MISSING")


async def test_a_kept_tutorial_insight_is_completed_like_any_other(browser, store, flow_settings):
    first = await browser.post("/tutorial/rain/insights/drop")
    again = await browser.post("/tutorial/rain/insights/drop")
    planting = await browser.post("/tutorial/rain/insights/planting")

    body = first.json()
    assert first.status_code == 200
    assert flow_settings.guest_cookie_name in first.headers["set-cookie"]
    assert first.headers["cache-control"] == "no-store"
    assert (body["origin"], body["engine"], body["label"]) == (
        "tutorial",
        "prepared",
        "مثال موثّق مُعدّ",
    )
    assert again.json()["id"] == body["id"]
    assert body["quran"]["verse"]["text"] == verse_text(30, 50)
    for insight in (body, planting.json()):
        await browser.post(f"/insights/{insight['id']}/complete")
    progress = (await browser.get("/me/progress")).json()
    earned = {badge["id"] for badge in progress["badges"] if badge["earned"]}
    assert "both-insights" in earned
    async with store() as db:
        (relation,) = (await db.scalars(select(WorldRelation))).all()
    assert relation.reason.value == "same_scene"


async def test_an_unknown_tutorial_insight_is_not_found(browser, store):
    unknown = await browser.post("/tutorial/rain/insights/sunset")
    malformed = await browser.post("/tutorial/rain/insights/Not_A_Slug")

    assert (unknown.status_code, unknown.json()["error"]) == (404, "NOT_FOUND")
    assert malformed.status_code == 422


async def test_a_tutorial_insight_without_a_hadith_shows_its_verse_alone(store, flow_settings):
    tutorial = load_tutorial()
    alone = tutorial.model_copy(
        update={
            "insights": [tutorial.insights[1].model_copy(update={"hadith": None, "slug": "alone"})]
        }
    )
    owner_key = "e" * 64
    async with store() as db:
        from src.models import Guest
        from src.owner import Owner

        db.add(Guest(key=owner_key))
        await db.flush()
        shown = await tutorial_service.describe(db, alone)
        kept = await tutorial_service.keep(db, Owner(guest_key=owner_key), alone, "alone")

    (insight,) = shown.insights
    assert (insight.hadith, insight.hadith_status, insight.pair_complete) == (None, "none", False)
    assert (kept.hadith_collection, kept.hadith_evidence) == (None, None)
    assert tutorial.insight("missing") is None


async def test_the_platform_words_of_the_tutorial_pass_the_leak_guard(store):
    async with store() as db:
        shown = await tutorial_service.describe(db, load_tutorial())
        corpus = [shown.insights[0].quran.verse.text, shown.insights[1].quran.verse.text]
        corpus += [hadith_text("bukhari", 1032), *(row["text"] for row in EXTRA["hadiths"])]
        guard = LeakGuard([PatternLeakDetector(), ShingleOverlapDetector(corpus)])
        for insight in load_tutorial().insights:
            texts = [
                insight.title,
                insight.glimpse,
                *(part.text for part in insight.explanation),
                *insight.why.visible_clues,
                *insight.why.limits,
                insight.why.concept,
                insight.small_step.text if insight.small_step else "",
            ]
            assert [text for text in texts if guard.check(text).leaked] == []
            assert not await repeats_store(db, texts)


def test_the_map_has_one_region_per_domain_and_never_moves_one():
    regions = load_regions()

    assert len(regions.regions) == 16
    assert {region.domain_id for region in regions.regions} == {f"T{n:02d}" for n in range(16)}
    assert regions.for_domain("T12").name == "بستان النفع"
    assert regions.for_domain(None).id == "T00"
    assert regions.for_domain("T99").id == "T00"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda d: d["regions"].append(dict(d["regions"][0])), "appears twice"),
        (
            lambda d: d["regions"].__setitem__(1, {**d["regions"][1], "domain_id": "T00"}),
            "two regions",
        ),
        (lambda d: d.__setitem__("fallback_region", "T99"), "fallback"),
    ],
)
def test_a_broken_map_file_is_refused(change, reason):
    data = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))
    change(data)

    with pytest.raises(ValidationError, match=reason):
        Regions.model_validate(data)
