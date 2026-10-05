"""The chat of an insight: three successful messages, counted once each, classified and guarded."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src import clock
from src.ai.errors import AiCallError, AiErrorCode
from src.errors import AppError
from src.messages import messages_for
from src.models import (
    AiCall,
    ChatMessage,
    ChatStatus,
    Guest,
    Hadith,
    HadithClassification,
    HadithVerificationQueue,
    QuranVerse,
)
from src.owner import Owner
from src.pipeline.insight.engine import ResourceCache
from src.scripture.text import search_copy
from src.services import chat_service
from src.services.chat_retrieval import query_for
from tests.fakes import FakeModelClient
from tests.retrieval.support import EmbeddingClient
from tests.scans.builders import insight_row, scan_row, scene
from tests.scans.conftest import as_guest, rule
from tests.scripture.fixtures import enrich_hadith


def said(
    level: str = "b", answer: str = "تدعو الآية إلى التأمل في أثر الرحمة.", new_text: bool = False
):
    return {"level": level, "asks_for_new_text": new_text, "answer": answer}


def wants(kind: str = "either") -> dict[str, Any]:
    """The model's answer when the learner asks for a text that is not shown."""
    return said(level="a", answer="", new_text=True) | {"new_text_kind": kind}


def relevant_where(word: str):
    """A verifier that finds relevant exactly the texts holding `word`, and nothing else."""

    def answer(call: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(call["user"])
        return {
            "candidates": [
                {
                    "candidate": item["candidate"],
                    "texts": [
                        {
                            "label": text["label"],
                            "relevant": word in text["text"],
                            "strength": "strong",
                            "relation": "direct",
                            "limit": "لا يثبت النص ما قبل الصورة",
                        }
                        for text in item["texts"]
                    ],
                }
                for item in payload["candidates"]
            ]
        }

    return answer


def labels(call: dict[str, Any]) -> list[str]:
    return [text["label"] for text in json.loads(call["user"])["candidates"][0]["texts"]]


async def an_insight(
    browser, store, flow_settings, *, with_scene: bool = False, **values: Any
) -> str:
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        stored = scene().model_dump(mode="json") if with_scene else None
        scan = scan_row(owner, status="done", scene=stored)
        db.add(scan)
        await db.flush()
        insight = insight_row(owner, scan_id=scan.id, **values)
        db.add(insight)
        await db.commit()
        return str(insight.id)


def searching_model(flow_app, *answers: Any) -> EmbeddingClient:
    """A model that embeds too, with the engine's indexes loaded from this test's store."""
    model = EmbeddingClient()
    model.answers = list(answers)

    def client_factory(log):
        model.log = log
        return model

    flow_app.state.model_client_factory = client_factory
    flow_app.state.engine_resources = ResourceCache()
    return model


async def stored_verse(store, surah: int, ayah: int) -> str:
    async with store() as db:
        text = await db.scalar(
            select(QuranVerse.text).where(QuranVerse.surah == surah, QuranVerse.ayah == ayah)
        )
    assert text is not None
    return text


async def stored_hadith(store, collection: str, number: str) -> str:
    async with store() as db:
        text = await db.scalar(
            select(Hadith.text).where(Hadith.collection == collection, Hadith.number == number)
        )
    assert text is not None
    return text


async def ask(
    browser, insight_id: str, message: str = "ما معنى الإحياء هنا؟", key: str = "key-0001"
):
    return await browser.post(
        f"/insights/{insight_id}/chat", json={"message": message, "idempotencyKey": key}
    )


async def test_a_question_is_answered_grounded_counted_and_disclosed(
    browser, store, flow_settings, model
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    model.answers.append(said())

    response = await ask(browser, insight_id)

    body = response.json()
    assert response.status_code == 200
    assert body["message"]["answer"] == "تدعو الآية إلى التأمل في أثر الرحمة."
    assert (body["message"]["level"], body["message"]["kind"]) == ("b", "answer")
    assert (body["used"], body["limit"], body["remaining"]) == (1, 3, 2)
    assert body["disclosure"] == messages_for().ai_disclosure
    call = model.calls[0]
    assert call["stage"].value == "chat"
    assert "ما معنى الإحياء هنا؟" in call["user"]
    assert "30:50" in call["user"]
    assert "1032" in call["user"]
    assert "قطرات على ورق نبتة." in call["user"]
    assert "Never write, quote" in call["system"]
    assert call["images"] == []
    async with store() as db:
        calls = (await db.scalars(select(AiCall))).all()
    assert [(c.stage, str(c.insight_id)) for c in calls] == [("chat", insight_id)]
    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]
    assert (shown["used"], shown["messages"][0]["question"]) == (1, "ما معنى الإحياء هنا؟")


async def test_the_same_key_is_answered_once_and_counted_once(browser, store, flow_settings, model):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.append(said())

    first = await ask(browser, insight_id, key="retry-key")
    again = await ask(browser, insight_id, message="سؤال آخر", key="retry-key")

    assert again.json()["message"] == first.json()["message"]
    assert again.json()["used"] == 1
    assert len(model.calls) == 1


async def test_done_closes_the_chat_and_keeps_what_was_said(browser, store, flow_settings, model):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.append(said())
    await ask(browser, insight_id, key="before-done")

    assert (await browser.post(f"/insights/{insight_id}/complete")).status_code == 200
    after = await ask(browser, insight_id, key="after-done")
    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]

    assert (after.status_code, after.json()["error"]) == (409, "CHAT_CLOSED")
    assert (shown["closed"], shown["used"]) == (True, 1)
    assert len(model.calls) == 1


async def test_the_fourth_message_is_refused(browser, store, flow_settings, model):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.extend([said(), said(), said()])

    answers = [await ask(browser, insight_id, key=f"key-000{n}") for n in range(3)]
    fourth = await ask(browser, insight_id, key="key-0004")

    assert [answer.json()["remaining"] for answer in answers] == [2, 1, 0]
    assert (fourth.status_code, fourth.json()["error"]) == (409, "CHAT_LIMIT_REACHED")
    assert fourth.json()["detail"] == messages_for().chat_limit_reached
    assert "Q: ما معنى الإحياء هنا؟" in model.calls[2]["user"]


async def test_a_message_being_answered_is_not_answered_twice_and_a_crashed_one_is_cleared(
    browser, store, flow_settings, model
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        db.add(
            ChatMessage(
                insight_id=int(insight_id),
                idempotency_key="in-flight",
                status=ChatStatus.PENDING,
                question="؟",
                created_at=clock.utcnow(),
            )
        )
        db.add(
            ChatMessage(
                insight_id=int(insight_id),
                idempotency_key="crashed-key",
                status=ChatStatus.PENDING,
                question="؟",
                created_at=clock.utcnow() - timedelta(minutes=10),
            )
        )
        await db.commit()
    model.answers.append(said())

    busy = await ask(browser, insight_id, key="in-flight")
    retried = await ask(browser, insight_id, key="crashed-key")

    assert (busy.status_code, busy.json()["error"]) == (409, "CHAT_IN_PROGRESS")
    assert retried.status_code == 200
    assert retried.json()["used"] == 1


@pytest.mark.parametrize(
    ("answer", "status", "code"),
    [
        (AiCallError(AiErrorCode.TIMEOUT, "slow"), 503, "MODEL_UNAVAILABLE"),
        (
            said(answer="قال تعالى: «فانظر إلى آثار رحمت الله كيف يحيي الأرض»"),
            502,
            "CHAT_ANSWER_REJECTED",
        ),
        (said(answer="   "), 502, "CHAT_ANSWER_REJECTED"),
    ],
)
async def test_a_failed_answer_gives_its_slot_back(
    browser, store, flow_settings, model, answer, status, code
):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.extend([answer, said()])

    failed = await ask(browser, insight_id)
    retried = await ask(browser, insight_id)

    assert (failed.status_code, failed.json()["error"]) == (status, code)
    assert retried.json()["used"] == 1
    async with store() as db:
        assert len((await db.scalars(select(AiCall))).all()) == 2


async def test_a_request_for_another_text_without_a_scene_to_judge_against_needs_a_new_scan(
    browser, store, flow_settings, model
):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.append(wants())

    body = (await ask(browser, insight_id, "أعطني حديثًا آخر عن المطر")).json()

    assert body["message"]["answer"] == messages_for().chat_needs_new_search
    assert body["message"]["kind"] == "new_search"
    assert (body["message"]["quran"], body["message"]["hadith"]) == (None, None)
    # No scene to verify against: nothing was searched, and no text is cited from memory.
    assert [call["stage"].value for call in model.calls] == ["chat"]


async def test_a_request_for_another_text_searches_again_verifies_and_shows_the_found_verse(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    model = searching_model(flow_app, wants("either"), relevant_where("نبات"))

    body = (await ask(browser, insight_id, "أعطني آية أخرى عن الماء والنبات")).json()

    message = body["message"]
    verse = message["quran"]["verse"]
    assert (verse["surah"], verse["ayah"]) == (6, 99)
    text = await stored_verse(store, 6, 99)
    assert verse["text"] == text
    assert verse["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert message["quran"]["tag"] == messages_for().quran_tag
    assert message["hadith"] is None
    assert message["answer"] == messages_for().chat_new_text_found.format(
        references=f"سورة {verse['surah_name']}، الآية 99"
    )
    assert (message["level"], message["kind"]) == ("a", "answer")
    assert text not in message["answer"]
    assert (body["used"], body["remaining"]) == (1, 2)
    # One embedding, one verifier call, both corpora searched, the insight's own texts left out.
    assert [call["stage"].value for call in model.calls] == ["chat", "verify"]
    assert model.embedded == [[query_for("الإحياء", "أعطني آية أخرى عن الماء والنبات")]]
    payload = json.loads(model.calls[1]["user"])
    assert payload["scene"]["description"] == "نبتة صغيرة تحت المطر"
    assert payload["candidates"][0]["concept"] == "الإحياء"
    shown = [label[0] for label in labels(model.calls[1])]
    assert "Q" in shown
    assert "H" in shown
    # The verifier reads folded search copies: the insight's own verse must not be among them.
    own_copy = search_copy(await stored_verse(store, 30, 50))
    other_copy = search_copy(await stored_verse(store, 6, 99))
    offered = [text["text"] for text in payload["candidates"][0]["texts"]]
    assert offered
    assert all(not text.startswith(own_copy[:30]) for text in offered)
    assert any(text.startswith(other_copy[:30]) for text in offered)
    async with store() as db:
        row = await db.scalar(select(ChatMessage))
        assert row is not None
        assert row.evidence_ids == ["quran:30:50", "quran:6:99"]
        # The fake embeds without a call record; the verifier call is recorded with the chat's.
        calls = (await db.scalars(select(AiCall))).all()
        assert sorted((c.stage, str(c.insight_id)) for c in calls) == [
            ("chat", insight_id),
            ("verify", insight_id),
        ]
    page = (await browser.get(f"/insights/{insight_id}")).json()["chat"]["messages"][0]
    assert page["quran"]["verse"]["text"] == text
    assert page["answer"] == message["answer"]


async def test_a_request_for_a_verse_searches_the_quran_alone_and_says_when_nothing_passes(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    model = searching_model(flow_app, wants("verse"), relevant_where("كلمة لا توجد في أي نص"))

    body = (await ask(browser, insight_id, "أعطني آية أخرى عن الماء والنبات")).json()

    assert body["message"]["answer"] == messages_for().chat_needs_new_search
    assert body["message"]["kind"] == "new_search"
    assert (body["message"]["quran"], body["message"]["hadith"]) == (None, None)
    assert [call["stage"].value for call in model.calls] == ["chat", "verify"]
    assert all(label.startswith("Q") for label in labels(model.calls[1]))
    async with store() as db:
        row = await db.scalar(select(ChatMessage))
        assert row is not None
        assert row.evidence_ids == ["quran:30:50"]


async def test_a_request_whose_searches_find_nothing_calls_no_verifier(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    model = searching_model(flow_app, wants("hadith"))

    body = (await ask(browser, insight_id, "xyzzy")).json()

    assert body["message"]["kind"] == "new_search"
    assert [call["stage"].value for call in model.calls] == ["chat"]


async def test_a_found_hadith_without_a_ruling_is_queued_and_never_shown(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    model = searching_model(flow_app, wants("hadith"), relevant_where("يغرس"))

    body = (await ask(browser, insight_id, "أعطني حديثًا عن الغرس والزرع")).json()

    assert body["message"]["answer"] == messages_for().chat_needs_new_search
    assert body["message"]["kind"] == "new_search"
    assert body["message"]["hadith"] is None
    assert all(label.startswith("H") for label in labels(model.calls[1]))
    async with store() as db:
        queued = (await db.scalars(select(HadithVerificationQueue))).all()
        wanted = await db.scalar(
            select(Hadith.id).where(Hadith.collection == "bukhari", Hadith.number == "2320")
        )
        assert [(q.hadith_id, q.demand_count) for q in queued] == [(wanted, 1)]
        row = await db.scalar(select(ChatMessage))
        assert row is not None
        assert row.evidence_ids == ["quran:30:50"]


async def test_a_found_hadith_with_an_eligible_ruling_is_shown_from_the_store_until_ruled_out(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    async with store() as db:
        await rule(db, "bukhari", "2320")
        await db.commit()
    searching_model(flow_app, wants("hadith"), relevant_where("يغرس"))

    body = (await ask(browser, insight_id, "أعطني حديثًا عن الغرس والزرع")).json()

    message = body["message"]
    hadith = message["hadith"]["hadith"]
    text = await stored_hadith(store, "bukhari", "2320")
    assert (hadith["collection"]["slug"], hadith["number"]) == ("bukhari", "2320")
    assert hadith["text"] == text
    assert hadith["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert hadith["eligible"] is True
    assert message["hadith"]["tag"] == messages_for().sunnah_tag
    assert message["quran"] is None
    assert message["answer"] == messages_for().chat_new_text_found.format(
        references=f"{hadith['collection']['name_ar']}، رقم 2320"
    )
    assert message["kind"] == "answer"
    async with store() as db:
        row = await db.scalar(select(ChatMessage))
        assert row is not None
        assert row.evidence_ids == ["hadith:bukhari:2320", "quran:30:50"]

    async with store() as db:
        await rule(db, "bukhari", "2320", HadithClassification.DAIF)
        await db.commit()

    page = (await browser.get(f"/insights/{insight_id}")).json()["chat"]["messages"][0]
    assert page["answer"] == messages_for().chat_answer_withdrawn
    assert (page["quran"], page["hadith"]) == (None, None)
    assert text not in json.dumps(page, ensure_ascii=False)


async def test_a_found_hadith_of_the_enriched_file_shows_before_any_ruling(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    async with store() as db:
        wanted = await db.scalar(
            select(Hadith.id).where(Hadith.collection == "bukhari", Hadith.number == "2320")
        )
        await enrich_hadith(db, wanted)
        await db.commit()
    searching_model(flow_app, wants("hadith"), relevant_where("يغرس"))

    body = (await ask(browser, insight_id, "أعطني حديثًا عن الغرس والزرع")).json()

    # Decision 58: shown from the store with no ruling, and counted for an editor.
    hadith = body["message"]["hadith"]["hadith"]
    text = await stored_hadith(store, "bukhari", "2320")
    assert (hadith["number"], hadith["ruling"], hadith["eligible"]) == ("2320", None, True)
    assert hadith["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    async with store() as db:
        queued = (await db.scalars(select(HadithVerificationQueue))).all()
        assert [q.hadith_id for q in queued] == [wanted]


async def test_a_verifier_that_fails_gives_the_slot_back(browser, store, flow_settings, flow_app):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    searching_model(flow_app, wants(), AiCallError(AiErrorCode.TIMEOUT, "slow"), said(), said())

    failed = await ask(browser, insight_id, "أعطني آية أخرى عن الماء والنبات")
    retried = await ask(browser, insight_id)

    assert (failed.status_code, failed.json()["error"]) == (503, "MODEL_UNAVAILABLE")
    assert retried.json()["used"] == 1
    async with store() as db:
        stages = sorted(c.stage for c in (await db.scalars(select(AiCall))).all())
    assert stages == ["chat", "chat", "verify"]


def test_the_query_keeps_the_concept_and_the_first_words_of_the_message():
    words = " ".join(f"كلمة{index}" for index in range(40))

    query = query_for("الإحياء", words)

    assert query.split()[0] == "الإحياء"
    assert len(query.split()) == 24
    assert query_for(" الإحياء ", " سؤال قصير ") == "الإحياء سؤال قصير"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            "الزواج عقد له أركان معروفة.",
            "الزواج عقد له أركان معروفة.\n\n" + messages_for().chat_referral,
        ),
        ("", messages_for().chat_referral),
    ],
)
async def test_a_personal_case_gets_general_information_and_a_referral(
    browser, store, flow_settings, model, answer, expected
):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.append(said(level="d", answer=answer))

    body = (await ask(browser, insight_id, "هل يصح زواجي في حالتي؟")).json()

    assert body["message"]["answer"] == expected
    assert (body["message"]["level"], body["message"]["kind"]) == ("d", "referral")


async def test_the_chat_can_be_switched_off_and_a_key_must_look_like_one(
    browser, store, flow_settings, flow_app, make_settings
):
    insight_id = await an_insight(browser, store, flow_settings)
    for key in ("short", "has spaces in it", "x" * 65):
        assert (await ask(browser, insight_id, key=key)).status_code == 422
    flow_app.state.settings = make_settings(feature_chat=False)

    off = await ask(browser, insight_id)

    assert (off.status_code, off.json()["error"]) == (404, "FEATURE_DISABLED")
    assert (await browser.get(f"/insights/{insight_id}")).json()["chat"]["enabled"] is False


class SlowModel(FakeModelClient):
    async def chat_json(self, schema, **kwargs):
        await asyncio.sleep(0.3)
        return await super().chat_json(schema, **kwargs)


async def test_concurrent_messages_are_counted_one_after_the_other(engine, make_settings):
    """Two connections at once, with one message left: exactly one is answered."""
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    key = "c" * 64
    owner = Owner(guest_key=key)
    async with maker() as db:
        db.add(Guest(key=key))
        await db.flush()
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        insight = insight_row(owner, scan_id=scan.id)
        db.add(insight)
        await db.commit()
    settings = make_settings(max_chat_user_messages=1)
    model = SlowModel(answers=[said(), said()])

    async def send(name: str):
        async with maker() as db:
            try:
                reply = await chat_service.answer(
                    db, settings, insight, question="؟", key=name, client_factory=lambda _log: model
                )
            except AppError as refused:
                return refused.code.value
            return reply.used

    try:
        results = await asyncio.gather(send("first-key"), send("second-key"))
    finally:
        async with maker() as db:
            await db.execute(delete(Guest).where(Guest.key == key))
            await db.commit()

    assert sorted(map(str, results)) == ["1", "CHAT_LIMIT_REACHED"]
    assert len(model.calls) == 1


async def test_an_answer_written_beside_a_hadith_since_ruled_out_is_hidden_and_never_sent_again(
    browser, store, flow_settings, model
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    model.answers.extend([said(answer="جواب أول عن الحديث."), said(answer="جواب ثان.")])
    await ask(browser, insight_id, message="سؤال أول", key="key-0001")
    async with store() as db:
        row = await db.scalar(select(ChatMessage))
        assert row is not None
        assert row.evidence_ids == ["hadith:bukhari:1032", "quran:30:50"]

    async with store() as db:
        await rule(db, "bukhari", "1032", HadithClassification.DAIF)
        await db.commit()

    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]
    assert [(m["question"], m["answer"]) for m in shown["messages"]] == [
        ("سؤال أول", messages_for().chat_answer_withdrawn)
    ]
    assert (shown["used"], shown["remaining"]) == (1, 2)
    replay = await ask(browser, insight_id, message="سؤال أول", key="key-0001")
    assert replay.json()["message"]["answer"] == messages_for().chat_answer_withdrawn
    assert "جواب أول عن الحديث." not in replay.text
    second = await ask(browser, insight_id, message="سؤال ثان", key="key-0002")
    assert second.json()["message"]["answer"] == "جواب ثان."
    assert "جواب أول عن الحديث." not in model.calls[1]["user"]
    assert "سؤال أول" not in model.calls[1]["user"]
    assert "1032" not in model.calls[1]["user"]
    assert "no hadith is shown" in model.calls[1]["system"]


async def test_an_answer_of_an_unknown_evidence_is_not_shown_and_one_still_shown_is(
    browser, store, flow_settings, model
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        for key, ids in (("old-key1", None), ("kept", ["quran:30:50"])):
            db.add(
                ChatMessage(
                    insight_id=int(insight_id),
                    idempotency_key=key,
                    status=ChatStatus.ANSWERED,
                    question=f"سؤال {key}",
                    answer=f"جواب {key}",
                    level="a",
                    kind="answer",
                    evidence_ids=ids,
                    answered_at=clock.utcnow(),
                )
            )
        await db.commit()

    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]

    assert [m["answer"] for m in shown["messages"]] == [
        messages_for().chat_answer_withdrawn,
        "جواب kept",
    ]
    assert shown["used"] == 2
    model.answers.append(said())
    await ask(browser, insight_id, message="سؤال جديد", key="key-0009")
    assert "old-key1" not in model.calls[0]["user"]
    assert "جواب kept" in model.calls[0]["user"]
    replay = await ask(browser, insight_id, key="old-key1")
    assert replay.json()["message"]["answer"] == messages_for().chat_answer_withdrawn


async def test_an_answer_whose_found_text_is_unknown_or_gone_from_the_store_is_withdrawn(
    browser, store, flow_settings
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        for key, ids in (
            ("odd-ref", ["quran:30:50", "masar:T01_01"]),
            ("gone-verse", ["quran:30:50", "quran:99:1"]),
            ("gone-hadith", ["quran:30:50", "hadith:bukhari:9999"]),
        ):
            db.add(
                ChatMessage(
                    insight_id=int(insight_id),
                    idempotency_key=key,
                    status=ChatStatus.ANSWERED,
                    question=f"سؤال {key}",
                    answer=f"جواب {key}",
                    level="a",
                    kind="answer",
                    evidence_ids=ids,
                    answered_at=clock.utcnow(),
                )
            )
        await db.commit()

    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]

    assert [m["answer"] for m in shown["messages"]] == [messages_for().chat_answer_withdrawn] * 3
    assert all((m["quran"], m["hadith"]) == (None, None) for m in shown["messages"])


@pytest.mark.parametrize("classification", [HadithClassification.SAHIH, HadithClassification.DAIF])
async def test_an_answer_written_while_its_hadith_awaited_a_ruling_stays_shown(
    browser, store, flow_settings, model, classification
):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.append(said(answer="جواب قبل الحكم."))
    await ask(browser, insight_id)
    async with store() as db:
        await rule(db, "bukhari", "1032", classification)
        await db.commit()

    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]

    assert [m["answer"] for m in shown["messages"]] == ["جواب قبل الحكم."]


class RulingWhileWriting(FakeModelClient):
    """A model whose answer takes long enough for an editor to rule the hadith out."""

    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self.store = store

    async def chat_json(self, schema, **kwargs):
        async with self.store() as db:
            await rule(db, "bukhari", "1032", HadithClassification.DAIF)
            await db.commit()
        return await super().chat_json(schema, **kwargs)


async def test_an_answer_written_while_its_hadith_was_ruled_out_is_refused_unread(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(browser, store, flow_settings)
    async with store() as db:
        await rule(db, "bukhari", "1032")
        await db.commit()
    model = RulingWhileWriting(store, answers=[said(answer="جواب عن الحديث."), said()])

    def client_factory(log):
        model.log = log
        return model

    flow_app.state.model_client_factory = client_factory

    refused = await ask(browser, insight_id, key="key-0001")
    retried = await ask(browser, insight_id, key="key-0002")

    assert (refused.status_code, refused.json()["error"]) == (502, "CHAT_ANSWER_REJECTED")
    assert "جواب عن الحديث." not in refused.text
    # The slot went back; the retry was written beside the verse alone and shows.
    assert (retried.status_code, retried.json()["used"]) == (200, 1)
    shown = (await browser.get(f"/insights/{insight_id}")).json()["chat"]
    assert [m["question"] for m in shown["messages"]] == ["ما معنى الإحياء هنا؟"]
    async with store() as db:
        rows = (await db.scalars(select(ChatMessage))).all()
        assert [row.evidence_ids for row in rows] == [["quran:30:50"]]
        assert len((await db.scalars(select(AiCall))).all()) == 2


async def test_a_request_for_a_text_still_searches_without_vectors_when_the_embedding_fails(
    browser, store, flow_settings, flow_app, caplog
):
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    model = searching_model(flow_app, wants("either"), relevant_where("نبات"))
    model.fail_on_call = 1

    with caplog.at_level(logging.WARNING, logger="tabsira.chat.retrieval"):
        body = (await ask(browser, insight_id, "أعطني آية أخرى عن الماء والنبات")).json()

    assert body["message"]["kind"] == "answer"
    assert [record.getMessage() for record in caplog.records] == [
        "query embedding skipped: timeout; searching without vectors"
    ]


async def test_a_request_for_a_text_keeps_the_fused_order_when_the_reranker_fails(
    browser, store, flow_settings, flow_app, make_settings, caplog
):
    flow_app.state.settings = make_settings(password_bcrypt_rounds=4, reranker="llm")
    insight_id = await an_insight(browser, store, flow_settings, with_scene=True)
    verifier = relevant_where("نبات")

    def answer(call: dict[str, Any]) -> Any:
        if call["stage"].value == "rerank":
            return AiCallError(AiErrorCode.TIMEOUT, "slow")
        return verifier(call)

    model = searching_model(flow_app, wants("either"), *[answer] * 5)

    with caplog.at_level(logging.WARNING, logger="tabsira.chat.retrieval"):
        body = (await ask(browser, insight_id, "أعطني آية أخرى عن الماء والنبات")).json()

    assert body["message"]["kind"] == "answer"
    assert "rerank" in [call["stage"].value for call in model.calls]
    assert "reranker skipped: timeout; fused order kept" in [
        record.getMessage() for record in caplog.records
    ]


async def test_an_insight_without_a_verse_or_a_hadith_leaves_nothing_out_of_the_search(
    browser, store, flow_settings, flow_app
):
    insight_id = await an_insight(
        browser,
        store,
        flow_settings,
        with_scene=True,
        quran_surah=None,
        quran_ayah=None,
        hadith_collection=None,
        hadith_number=None,
    )
    searching_model(flow_app, wants("either"), relevant_where("نبات"))

    body = (await ask(browser, insight_id, "أعطني آية أخرى عن الماء والنبات")).json()

    assert body["message"]["kind"] == "answer"
