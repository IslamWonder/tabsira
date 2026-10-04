"""The chat of an insight: three successful messages, counted once each, classified and guarded."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src import clock
from src.ai.errors import AiCallError, AiErrorCode
from src.errors import AppError
from src.messages import messages_for
from src.models import AiCall, ChatMessage, ChatStatus, Guest, HadithClassification
from src.owner import Owner
from src.services import chat_service
from tests.fakes import FakeModelClient
from tests.scans.builders import insight_row, scan_row
from tests.scans.conftest import as_guest, rule


def said(
    level: str = "b", answer: str = "تدعو الآية إلى التأمل في أثر الرحمة.", new_text: bool = False
):
    return {"level": level, "asks_for_new_text": new_text, "answer": answer}


async def an_insight(browser, store, flow_settings) -> str:
    owner = await as_guest(browser, store, flow_settings)
    async with store() as db:
        scan = scan_row(owner, status="done")
        db.add(scan)
        await db.flush()
        insight = insight_row(owner, scan_id=scan.id)
        db.add(insight)
        await db.commit()
        return str(insight.id)


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


async def test_a_request_for_another_text_needs_a_new_search(browser, store, flow_settings, model):
    insight_id = await an_insight(browser, store, flow_settings)
    model.answers.append(said(level="a", answer="", new_text=True))

    body = (await ask(browser, insight_id, "أعطني حديثًا آخر عن المطر")).json()

    assert body["message"]["answer"] == messages_for().chat_needs_new_search
    assert body["message"]["kind"] == "new_search"


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
