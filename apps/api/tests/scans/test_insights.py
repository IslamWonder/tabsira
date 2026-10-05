"""An insight as its owner reads it: scripture from the store by reference, the step declared."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from src.models import EvidenceExposure, HadithClassification, Profile
from src.owner import Owner
from src.services import learner_service
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, make_account, rule, sign_in
from tests.scripture.fixtures import hadith_text, verse_text


async def keep(store, owner: Owner, *, scan: bool = True, **values) -> int:
    async with store() as db:
        if scan:
            row = scan_row(owner, status="done", **values.pop("scan_values", {}))
            db.add(row)
            await db.flush()
            values.setdefault("scan_id", row.id)
        insight = insight_row(owner, **values)
        db.add(insight)
        await db.commit()
        return insight.id


async def test_an_insight_shows_its_verse_exactly_as_stored_and_waits_for_its_hadith_ruling(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(store, owner)

    response = await browser.get(f"/insights/{insight_id}")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    verse = body["quran"]["verse"]
    assert body["quran"]["tag"] == "القرآن"
    assert verse["text"] == verse_text(30, 50)
    assert hashlib.sha256(verse["text"].encode()).hexdigest() == verse["sha256"]
    assert verse["status"] == "verified_cached"
    assert verse["links"]["quranpedia"].startswith("https://quranpedia.net/surah/2/30#verse-")
    assert body["quran"]["why"] == {
        "relation": "direct",
        "relation_label": "صلة مباشرة",
        "matched_on": "إحياء الأرض",
    }
    assert body["hadith"] is None
    assert body["hadith_status"] == "awaiting_verification"
    assert "بانتظار التحقق" in body["notice"]
    assert body["pair_complete"] is False
    # The step rests on the hadith, which is not shown yet.
    assert body["small_step"] is None
    assert body["explanation_tag"] == "شرح تبصرة"
    assert body["explanation"] == [
        {"section": "seen", "label": "ما ظهر", "text": "قطرات على ورق نبتة."}
    ]
    assert body["label"] is None
    assert body["chat"] == {
        "enabled": True,
        "used": 0,
        "limit": 3,
        "remaining": 3,
        "closed": False,
        "messages": [],
    }
    assert body["learning_unit"]["domain_id"] == "T01"
    assert body["image"] == {
        "sensitive": False,
        "url": f"/scans/{body['scan_id']}/image",
        "has_photo": False,
    }
    assert body["disclosure"].startswith("تبصرة أداة مدعومة")
    for private in ("religious_background", "gender", "age_range", "goals"):
        assert private not in response.text


async def test_reading_an_insight_records_each_text_as_shown_once(
    browser, other, store, flow_settings
):
    """v2 §11 and masar §10.5: what was shown is recorded when it is shown, once per text."""
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(store, owner)

    assert (await browser.get(f"/insights/{insight_id}")).status_code == 200
    assert (await browser.get(f"/insights/{insight_id}")).status_code == 200
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    assert (await browser.get(f"/insights/{insight_id}")).json()["hadith_status"] == "shown"
    assert (await browser.get(f"/insights/{insight_id}")).status_code == 200
    assert (await other.get(f"/insights/{insight_id}")).status_code == 404

    async with store() as db:
        rows = (await db.scalars(select(EvidenceExposure).order_by(EvidenceExposure.at))).all()
        context = await learner_service.learner_context(db, owner)
    # One row for the verse on the first display, one for the hadith once its ruling shows it.
    assert [
        (r.kind, r.insight_id, r.quran_surah, r.quran_ayah, r.hadith_collection, r.hadith_number)
        for r in rows
    ] == [
        ("shown", insight_id, 30, 50, None, None),
        ("shown", insight_id, None, None, "bukhari", "1032"),
    ]
    assert {r.guest_key for r in rows} == {owner.guest_key}
    assert [(r.concept, r.learning_unit_id) for r in rows] == [("الإحياء", "T01_06")] * 2
    # The engine's diversity reads the displayed texts, not only the completed ones.
    assert [(ref.surah, ref.ayah) for ref in context.seen_quran] == [(30, 50)]
    assert [(ref.collection, ref.number) for ref in context.seen_hadith] == [("bukhari", "1032")]


async def test_no_display_is_recorded_while_memory_is_off_or_nothing_shows(
    browser, store, flow_settings
):
    user = await make_account(store)
    await sign_in(browser)
    owner = Owner(user_id=user.id)
    async with store() as db:
        (await db.get(Profile, user.id)).memory_enabled = False
        await db.commit()
    remembered = await keep(store, owner)
    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        await db.commit()
    bare = await keep(
        store,
        owner,
        quran_surah=None,
        quran_ayah=None,
        quran_evidence=None,
        explanation=[],
        small_step=None,
    )

    assert (await browser.get(f"/insights/{remembered}")).status_code == 200
    async with store() as db:
        assert (await db.scalars(select(EvidenceExposure))).all() == []
        (await db.get(Profile, user.id)).memory_enabled = True
        await db.commit()
    assert (await browser.get(f"/insights/{bare}")).json()["quran"] is None

    async with store() as db:
        assert (await db.scalars(select(EvidenceExposure))).all() == []


async def test_a_ruled_hadith_is_shown_whole_with_its_spans_ruling_and_links(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(store, owner)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()

    body = (await browser.get(f"/insights/{insight_id}")).json()

    hadith = body["hadith"]["hadith"]
    assert body["hadith"]["tag"] == "السنة"
    assert hadith["text"] == hadith_text("bukhari", 1032)
    assert hashlib.sha256(hadith["text"].encode()).hexdigest() == hadith["sha256"]
    assert "".join(hadith["text"][s["start"] : s["end"]] for s in hadith["spans"]) == hadith["text"]
    assert hadith["ruling"]["classification"] == "صحيح"
    assert hadith["links"]["dorar_verification"].startswith("https://dorar.net/hadith/search?q=")
    assert hadith["status"] == "local_corpus"
    assert (body["hadith_status"], body["notice"], body["pair_complete"]) == ("shown", None, True)
    assert body["small_step"] == {
        "text": "احفظ الدعاء الوارد في الحديث.",
        "kind": "text_grounded",
        "label": "من السنة",
    }


async def test_a_weak_hadith_is_never_shown_and_a_step_without_grounding_is_a_suggestion(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(
        store,
        owner,
        small_step={"text": "اسقِ نبتة اليوم.", "kind": "ethical_application", "grounded_in": []},
        engine="demo",
    )
    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        await db.commit()

    body = (await browser.get(f"/insights/{insight_id}")).json()

    assert (body["hadith"], body["hadith_status"], body["notice"]) == (None, "none", None)
    assert body["small_step"]["label"] == "اقتراح عملي"
    assert "محاكاة" in body["label"]


async def test_an_insight_of_a_sensitive_scene_has_no_photo_and_one_without_sources_still_reads(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    sensitive = await keep(store, owner, scan_values={"sensitive": True})
    bare = await keep(
        store,
        owner,
        quran_surah=None,
        quran_ayah=None,
        quran_evidence=None,
        hadith_collection=None,
        hadith_number=None,
        hadith_evidence=None,
        small_step=None,
        anchor={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        learning_unit_id="T99_99",
    )
    other_path = await keep(store, owner, learning_path_version=None)

    first = (await browser.get(f"/insights/{sensitive}")).json()
    second = (await browser.get(f"/insights/{bare}")).json()
    third = (await browser.get(f"/insights/{other_path}")).json()

    assert first["image"] == {"sensitive": True, "url": None, "has_photo": False}
    assert (second["quran"], second["hadith"], second["small_step"]) == (None, None, None)
    assert second["anchor"] == {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}
    assert second["learning_unit"] is None
    assert third["learning_unit"] is None


async def test_only_the_owner_reads_or_acts_on_an_insight(browser, other, store, flow_settings):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(store, owner)
    await make_account(store)
    await sign_in(other)

    for method, path, body in (
        ("GET", f"/insights/{insight_id}", None),
        ("POST", f"/insights/{insight_id}/action", {"choice": "done"}),
        ("POST", f"/insights/{insight_id}/complete", None),
        (
            "POST",
            f"/insights/{insight_id}/chat",
            {"message": "لماذا؟", "idempotencyKey": "key-0001"},
        ),
    ):
        response = await other.request(method, path, json=body)
        assert (response.status_code, response.json()["error"]) == (404, "NOT_FOUND")
    browser.cookies.clear()
    assert (await browser.get(f"/insights/{insight_id}")).status_code == 404
    assert (await other.get(f"/insights/{7_314_159_265_358_979_323}")).status_code == 404


@pytest.mark.parametrize(
    ("choices", "state", "means"),
    [
        (["later"], "later", "حُفظ تأجيلك"),
        (["later", "done"], "done", "تصريح منك بما فعلت"),
        (["done", "done"], "done", "تصريح منك بما فعلت"),
    ],
)
async def test_the_small_step_is_a_declaration_never_a_proof(
    browser, store, flow_settings, choices, state, means
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(store, owner)

    answers = [
        (await browser.post(f"/insights/{insight_id}/action", json={"choice": choice})).json()
        for choice in choices
    ]

    assert answers[-1]["state"] == state
    assert answers[-1]["means"].startswith(means)
    if choices == ["done", "done"]:
        assert answers[0]["at"] == answers[1]["at"]
    body = (await browser.get(f"/insights/{insight_id}")).json()
    assert body["action"]["state"] == state
    assert (
        await browser.post(f"/insights/{insight_id}/action", json={"choice": "maybe"})
    ).status_code == 422


async def test_a_hadith_alone_is_shown_when_it_is_the_only_verified_text(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    insight_id = await keep(
        store, owner, quran_surah=None, quran_ayah=None, quran_evidence=None, hadith_evidence=None
    )
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()

    body = (await browser.get(f"/insights/{insight_id}")).json()

    assert body["quran"] is None
    assert body["hadith"]["why"] is None
    assert body["small_step"]["label"] == "من السنة"
    assert body["pair_complete"] is False


def test_the_chat_talks_to_the_active_provider_on_one_shared_client(flow_settings):
    from fastapi import FastAPI
    from starlette.requests import Request

    from src.ai.client import ProviderClient
    from src.ai.records import CallLog
    from src.routers.insights import model_client_factory

    app = FastAPI()
    factory = model_client_factory(Request({"type": "http", "app": app}), flow_settings)
    client = factory(CallLog())
    again = model_client_factory(Request({"type": "http", "app": app}), flow_settings)

    assert isinstance(client, ProviderClient)
    assert client.provider == flow_settings.ai_provider
    assert again(CallLog())._http is app.state.http


async def test_an_insight_names_the_sound_of_its_first_ontology_entity(
    browser, store, flow_settings
):
    owner = await as_guest(browser, store, flow_settings)
    why = {"visible_clues": [], "concept": "الإحياء", "limits": []}
    with_sound = await keep(
        store, owner, why={**why, "ontology_entity_ids": ["not-an-id", "E006", "E007"]}
    )
    without_sound = await keep(store, owner, why=why)

    assert (await browser.get(f"/insights/{with_sound}")).json()["sound_url"] == (
        "/sounds/ontology/E006"
    )
    assert (await browser.get(f"/insights/{without_sound}")).json()["sound_url"] is None
