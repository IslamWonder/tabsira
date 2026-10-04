"""Nothing is said about a text that is not shown."""

from __future__ import annotations

from src.routers.scripture import read_verse
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


async def test_a_step_is_from_the_sunnah_only_with_a_hadith_shown(store):
    async with store() as db:
        verse = await read_verse(db, 30, 50)
    from_verse = {"text": "تأمّل.", "kind": "reflection", "grounded_in": ["quran:30:50"]}

    step = step_out(from_verse, verse, None)

    assert step is not None
    assert step.label == "اقتراح عملي"
    assert step_out(from_verse, None, None) is None


async def test_a_hidden_hadith_hides_its_section_on_an_insight(browser, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
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


async def test_the_tutorial_says_nothing_of_a_hadith_before_its_ruling(browser, store):
    waiting = (await browser.get("/tutorial/rain")).json()["insights"][0]
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    ruled = (await browser.get("/tutorial/rain")).json()["insights"][0]

    assert [part["section"] for part in waiting["explanation"]] == ["seen", "value", "quran"]
    assert [part["section"] for part in ruled["explanation"]] == [
        "seen",
        "value",
        "quran",
        "sunnah",
        "life",
    ]
