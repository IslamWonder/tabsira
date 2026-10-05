"""Nothing is said about a text that is not shown."""

from __future__ import annotations

from typing import Any

import pytest

from src.models import HadithClassification
from src.routers.scripture import read_hadith, read_verse
from src.services.insight_view import explanation_out, step_out
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, rule


def test_what_is_said_about_a_text_waits_with_it():
    parts = [
        {"section": "seen", "text": "قطرات."},
        {"section": "quran", "text": "الآية."},
        {"section": "sunnah", "text": "الحديث."},
        {"section": "life", "text": "ادع.", "sources": ["hadith:bukhari:1032", "T01_06"]},
        {"section": "value", "text": "نعمة.", "sources": ["masar:T01_06"]},
    ]

    shown = [part.section for part in explanation_out(parts, None, None)]

    assert shown == ["seen", "value"]


async def test_a_reference_the_view_cannot_place_counts_as_hidden(store):
    async with store() as db:
        verse = await read_verse(db, 30, 50)
    parts = [
        {"section": "seen", "text": "بلا مرجع.", "sources": ["T01_06"]},
        {"section": "value", "text": "مذكرة.", "sources": ["note:rain"]},
        {"section": "value", "text": "وحدة.", "sources": ["masar:T01_06"]},
        {"section": "value", "text": "وحدة مشوهة.", "sources": ["masar:../T01"]},
        {"section": "quran", "text": "الآية.", "sources": ["quran:30:50"]},
        {"section": "quran", "text": "آية أخرى.", "sources": ["quran:2:255"]},
    ]
    step = {"text": "تأمّل.", "kind": "reflection", "grounded_in": ["note:rain"]}

    shown = [part.text for part in explanation_out(parts, verse, None)]

    assert shown == ["وحدة.", "الآية."]
    assert step_out(step, verse, None) is None


async def test_a_step_is_from_the_sunnah_only_with_a_hadith_shown(store):
    async with store() as db:
        verse = await read_verse(db, 30, 50)
    from_verse = {"text": "تأمّل.", "kind": "reflection", "grounded_in": ["quran:30:50"]}

    step = step_out(from_verse, verse, None)

    assert step is not None
    assert step.label == "اقتراح عملي"
    assert step_out(from_verse, None, None) is None


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("text_grounded", "من السنة"),
        ("ethical_application", "اقتراح عملي"),
        ("reflection", "اقتراح عملي"),
    ],
)
async def test_only_a_practice_the_shown_hadith_grounds_is_from_the_sunnah(store, kind, label):
    async with store() as db:
        await rule(db, "bukhari", "1032")
        hadith = await read_hadith(db, "bukhari", "1032")
    step = {"text": "ادع.", "kind": kind, "grounded_in": ["hadith:bukhari:1032"]}

    shown = step_out(step, None, hadith)

    assert shown is not None
    assert shown.label == label


async def test_a_hadith_ruled_out_hides_its_section_on_an_insight(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        insight = insight_row(
            owner,
            scan_id=scan.id,
            explanation=[
                {"section": "quran", "text": "الآية.", "sources": []},
                {"section": "sunnah", "text": "الحديث.", "sources": []},
            ],
        )
        db.add(insight)
        await db.commit()

    body = (await browser.get(f"/insights/{insight.id}")).json()

    assert [part["section"] for part in body["explanation"]] == ["quran"]


async def test_the_tutorial_shows_a_hadith_with_no_ruling_and_says_nothing_of_one_ruled_out(
    browser, store
):
    unruled = (await browser.get("/tutorial/rain")).json()["insights"]
    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        await rule(db, "bukhari", "2320", HadithClassification.MAWDU)
        await db.commit()
    ruled_out = (await browser.get("/tutorial/rain")).json()["insights"]

    def sections(insight: dict[str, Any]) -> list[str]:
        return [part["section"] for part in insight["explanation"]]

    assert [sections(insight) for insight in unruled] == [
        ["seen", "value", "quran", "sunnah", "life"],
        ["seen", "value", "quran", "sunnah", "life"],
    ]
    # The drop's life part names its hadith; the planting's value part restates its own.
    assert [sections(insight) for insight in ruled_out] == [
        ["seen", "value", "quran"],
        ["seen", "quran", "life"],
    ]
