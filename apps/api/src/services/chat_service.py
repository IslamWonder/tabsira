"""
The chat of an insight (v2 §14): three successful messages, classified, grounded, guarded.

Counting is done by the database, atomically: the insight's row is locked
while a slot is reserved, so concurrent sends are counted one after the other.
A message is identified by its idempotency key: sending it again (a retry, a
refresh, a double click) returns the same answer and counts nothing; sending it
while its answer is being written answers CHAT_IN_PROGRESS. A slot is held by a
pending row while the model answers and given back if the answer fails, so
only successful messages count; a pending row older than CHAT_RESERVATION is
the remains of a crash and is cleared. The fourth message answers
CHAT_LIMIT_REACHED. «تمّ» closes the insight: its messages stay readable and a
new one answers CHAT_CLOSED.

The model writes the level of the question (v2 §12) before its answer. A
request for another text is never answered from memory: the app runs the
retrieval and the verification again for it (`chat_retrieval`, v2 §14) and,
when a text passes the gate, answers in its own words naming the text by
reference and attaches its evidence id, so the view reads it from the store;
when nothing passes, it says so. A personal case (level د) gets general
information and the app's referral. Every text shown goes through the leak
guard, with the insight's own texts as a corpus, and carries the disclosure.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.ai.client import ModelClient
from src.ai.errors import AiCallError
from src.ai.records import CallLog
from src.config import AiStage, Settings
from src.errors import AppError, ErrorCode
from src.messages import messages_for
from src.models import ChatMessage, ChatStatus, Hadith, Insight, QuranVerse
from src.pipeline.engine import LearnerContext
from src.pipeline.insight.composer import BACKGROUND_UNKNOWN, learner_view
from src.pipeline.insight.engine import SHARED_RESOURCES, ResourceCache
from src.pipeline.leak_guard import LeakGuard, PatternLeakDetector, ShingleOverlapDetector
from src.pipeline.prompt import load_prompt
from src.routers.scripture import HadithOut, QuranVerseOut
from src.scans.accept import verse_skeletons
from src.scans.workflow import call_rows
from src.schemas.insight import ChatReply
from src.scripture.guard_fold import guard_fold
from src.scripture.overlap import repeats_store
from src.services import chat_retrieval, learner_service
from src.services.chat_retrieval import NewText, TextKind
from src.services.insight_view import (
    answer_is_shown,
    explanation_out,
    message_out,
    shown_evidence,
    shown_ids,
    step_out,
)

SYSTEM_PROMPT = "insight_chat_system.v8"
USER_PROMPT = "insight_chat_user.v2"
MAX_OUTPUT_TOKENS = 1200
# What the system prompt says of a learner who declared nothing, or keeps personalization off.
NOTHING_DECLARED = "none"
# What a prompt section shows when it has nothing to say.
NO_TEXT = "(none)"
# A pending answer older than this was left by a crash; its slot is given back.
CHAT_RESERVATION = timedelta(minutes=5)

ClientFactory = Callable[[CallLog], ModelClient]


class ChatModelOutput(BaseModel):
    """The level first, then the answer: the classification governs what the answer may be."""

    level: Annotated[
        Literal["a", "b", "c", "d"],
        Field(
            description="a fixed fact; b explanation; c differed or sensitive; d fatwa or personal case"
        ),
    ]
    asks_for_new_text: Annotated[
        bool,
        Field(description="True when the learner asks for a verse or hadith that is not shown"),
    ]
    new_text_kind: Annotated[
        TextKind,
        Field(description="What is asked for when asks_for_new_text: verse, hadith, or either"),
    ] = "either"
    answer: Annotated[
        str, Field(description="Arabic, at most 120 words; empty when asks_for_new_text")
    ]


def _refused(code: ErrorCode, detail: str, status_code: int) -> AppError:
    return AppError(code, detail, status_code=status_code)


async def _reserve(
    db: AsyncSession, settings: Settings, insight: Insight, key: str, question: str
) -> ChatMessage:
    """Hold a slot for one message, or return the answered message of the same key."""
    # The lock also re-reads `completed_at`: a completion committed since the
    # caller loaded the row must close the insight here, not be missed. An
    # insight gone meanwhile (a scan run again drops its unfinished insights)
    # is not found, rather than a message held for a row that no longer exists.
    locked = (
        await db.execute(
            select(Insight.id, Insight.completed_at)
            .where(Insight.id == insight.id)
            .with_for_update()
        )
    ).one_or_none()
    if locked is None:
        await db.commit()
        raise _refused(ErrorCode.NOT_FOUND, "No such insight.", 404)
    completed_at = locked.completed_at
    stale_before = clock.utcnow() - CHAT_RESERVATION
    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.insight_id == insight.id,
            ChatMessage.status == ChatStatus.PENDING,
            ChatMessage.created_at < stale_before,
        )
    )
    existing: ChatMessage | None = await db.scalar(
        select(ChatMessage).where(
            ChatMessage.insight_id == insight.id, ChatMessage.idempotency_key == key
        )
    )
    if existing is not None:
        if existing.status is ChatStatus.PENDING:
            await db.commit()
            raise _refused(ErrorCode.CHAT_IN_PROGRESS, "This message is being answered.", 409)
        await db.commit()
        return existing
    held = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.insight_id == insight.id)
    )
    # «تمّ» closes the insight: what was discussed stays readable, nothing new is asked.
    if completed_at is not None:
        await db.commit()
        raise _refused(ErrorCode.CHAT_CLOSED, messages_for().chat_closed, 409)
    if int(held or 0) >= settings.max_chat_user_messages:
        await db.commit()
        raise _refused(ErrorCode.CHAT_LIMIT_REACHED, messages_for().chat_limit_reached, 409)
    row = ChatMessage(
        insight_id=insight.id,
        idempotency_key=key,
        status=ChatStatus.PENDING,
        question=question,
        created_at=clock.utcnow(),
    )
    db.add(row)
    await db.commit()
    return row


async def _history(db: AsyncSession, insight: Insight, shown: set[str]) -> str:
    """Return the answers whose texts are all still shown; the others never reach the model."""
    rows = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.insight_id == insight.id, ChatMessage.status == ChatStatus.ANSWERED)
            .order_by(ChatMessage.id)
        )
    ).all()
    kept = [row for row in rows if answer_is_shown(row, shown)]
    if not kept:
        return NO_TEXT
    return "\n".join(f"- Q: {row.question}\n  A: {row.answer}" for row in kept)


async def _cited_skeletons(db: AsyncSession, insight: Insight) -> list[str]:
    """
    Return the guard skeletons of the texts the insight cites, shown or not, for the leak guard.

    A hadith that is not shown (an editor ruled it out, decision 65) is guarded against all
    the same: the model must not quote it either. The verse is guarded in today's spelling
    too (its converted skeleton, task 05.9), which is never shown nor sent to the model.
    """
    texts: list[str | None] = []
    if insight.quran_surah is not None and insight.quran_ayah is not None:
        verse: str | None = await db.scalar(
            select(QuranVerse.text).where(
                QuranVerse.surah == insight.quran_surah, QuranVerse.ayah == insight.quran_ayah
            )
        )
        texts.extend(verse_skeletons(verse) if verse is not None else [])
    if insight.hadith_collection is not None and insight.hadith_number is not None:
        hadith: str | None = await db.scalar(
            select(Hadith.text).where(
                Hadith.collection == insight.hadith_collection,
                Hadith.number == insight.hadith_number,
            )
        )
        texts.append(guard_fold(hadith) if hadith is not None else None)
    return [text for text in texts if text is not None]


def _shown_texts(verse: QuranVerseOut | None, hadith: HadithOut | None) -> str:
    """Say which texts the learner sees, so the model never names one that is not shown."""
    if verse is not None and hadith is not None:
        return "a verse and a hadith are shown; call them «الآية المعروضة» and «الحديث المعروض»."
    if verse is not None:
        return "a verse is shown and no hadith is shown; call it «الآية المعروضة»."
    if hadith is not None:
        return "a hadith is shown and no verse is shown; call it «الحديث المعروض»."
    return "no verse and no hadith is shown."


def _explanation(verse: QuranVerseOut | None, hadith: HadithOut | None, insight: Insight) -> str:
    """Return the explanation the learner sees: nothing said about a text not shown."""
    parts = explanation_out(insight.explanation, verse, hadith)
    return "\n".join(f"- {part.section}: {part.text}" for part in parts) or NO_TEXT


def _step(verse: QuranVerseOut | None, hadith: HadithOut | None, insight: Insight) -> str:
    step = step_out(insight.small_step, verse, hadith)
    return f"- {step.label}: {step.text}" if step is not None else NO_TEXT


def _learner(learner: LearnerContext) -> str:
    """
    Return the profile fields the learner declared: the composer's, and the declared gender.

    The chat is private to its owner, so it alone may address a declared gender (decision 64).
    """
    shared = learner_view(learner)
    if learner.personalization_enabled and learner.gender != BACKGROUND_UNKNOWN:
        shared["gender"] = learner.gender
    return json.dumps(shared, ensure_ascii=False) if shared else NOTHING_DECLARED


def _why(insight: Insight) -> str:
    why = insight.why
    clues = "، ".join(why.get("visible_clues", [])) or "-"
    limits = "؛ ".join(why.get("limits", [])) or "-"
    return f"- clues: {clues}\n- concept: {why.get('concept', '-')}\n- limits: {limits}"


async def answer(
    db: AsyncSession,
    settings: Settings,
    insight: Insight,
    *,
    question: str,
    key: str,
    client_factory: ClientFactory,
    http: httpx.AsyncClient | None = None,
    resources: ResourceCache | None = None,
) -> ChatReply:
    """
    Answer one message of the insight's chat, or replay the answer of its key.

    `http` and `resources` serve a request for another text: the reranker that
    needs an HTTP client, and the engine's shared indexes (one per process).
    """
    question = question.strip()
    row = await _reserve(db, settings, insight, key, question)
    if row.status is ChatStatus.PENDING:
        await _answer(
            db,
            settings,
            insight,
            row,
            client_factory,
            http=http,
            resources=resources or SHARED_RESOURCES,
        )
    used = await _used(db, insight)
    limit = settings.max_chat_user_messages
    verse, hadith = await shown_evidence(db, insight)
    return ChatReply(
        message=await message_out(db, row, shown_ids(verse, hadith)),
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
        disclosure=messages_for().ai_disclosure,
    )


async def _used(db: AsyncSession, insight: Insight) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.insight_id == insight.id, ChatMessage.status == ChatStatus.ANSWERED)
    )
    return int(count or 0)


async def _answer(
    db: AsyncSession,
    settings: Settings,
    insight: Insight,
    row: ChatMessage,
    client_factory: ClientFactory,
    *,
    http: httpx.AsyncClient | None,
    resources: ResourceCache,
) -> None:
    verse, hadith = await shown_evidence(db, insight)
    references: list[str] = []
    corpus = await _cited_skeletons(db, insight)
    if verse is not None:
        references.append(f"{verse.surah_name} {verse.surah}:{verse.ayah}")
    if hadith is not None:
        references.append(f"{hadith.collection.name_ar} {hadith.number}")
    user = load_prompt(USER_PROMPT).render(
        title=insight.title,
        glimpse=insight.glimpse,
        relation=insight.relation,
        references="; ".join(references) or NO_TEXT,
        explanation=_explanation(verse, hadith, insight),
        why=_why(insight),
        step=_step(verse, hadith, insight),
        history=await _history(db, insight, shown_ids(verse, hadith)),
        question=row.question,
    )
    learner = await learner_service.profile_context(db, insight.user_id)
    log = CallLog()
    client = client_factory(log)
    try:
        result = await client.chat_json(
            ChatModelOutput,
            stage=AiStage.CHAT,
            system=load_prompt(SYSTEM_PROMPT).render(
                shown_texts=_shown_texts(verse, hadith), learner=_learner(learner)
            ),
            user=user,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except AiCallError:
        await _give_back(db, row, log, insight.id)
        raise _refused(ErrorCode.MODEL_UNAVAILABLE, "The chat model did not answer.", 503) from None
    output = result.value
    found = NewText()
    if output.asks_for_new_text:
        try:
            found = await chat_retrieval.find_new_text(
                db,
                settings,
                insight,
                client,
                question=row.question,
                kind=output.new_text_kind,
                http=http,
                resources=resources,
            )
        except AiCallError:
            await _give_back(db, row, log, insight.id)
            raise _refused(
                ErrorCode.MODEL_UNAVAILABLE, "The verifier did not answer.", 503
            ) from None
    text, kind = _compose(output, found)
    # Every text shown meets the guard, the app's own words included: patterns, the
    # insight's texts, then the whole store.
    guard = LeakGuard([PatternLeakDetector(), ShingleOverlapDetector(skeletons=corpus)])
    leaked = guard.check(text).leaked or await repeats_store(db, [text])
    if not text.strip() or leaked:
        await _give_back(db, row, log, insight.id)
        raise _refused(ErrorCode.CHAT_ANSWER_REJECTED, "The answer was refused.", 502)
    # An editor may have ruled while the model wrote: an answer about texts that
    # are no longer the ones shown is refused before anyone reads it.
    verse_now, hadith_now = await shown_evidence(db, insight)
    shown = shown_ids(verse, hadith)
    if shown_ids(verse_now, hadith_now) != shown:
        await _give_back(db, row, log, insight.id)
        raise _refused(
            ErrorCode.CHAT_ANSWER_REJECTED,
            "The texts shown changed while the answer was written.",
            502,
        )
    row.status = ChatStatus.ANSWERED
    row.answer = text
    row.level = output.level
    row.kind = kind
    row.evidence_ids = sorted(shown | found.ids)
    row.answered_at = clock.utcnow()
    db.add_all(call_rows(log.records, insight_id=insight.id))
    await db.commit()


def _compose(output: ChatModelOutput, found: NewText) -> tuple[str, str]:
    """
    Return the text shown and its kind: the app's own words for a new text, a referral for د.

    A text found for a request for another text is named by its reference only; the
    view reads it from the store beside the answer. Nothing found is said plainly.
    """
    if output.asks_for_new_text:
        if found.passed:
            return (
                messages_for().chat_new_text_found.format(references=_references(found)),
                "answer",
            )
        return messages_for().chat_needs_new_search, "new_search"
    if output.level == "d":
        general = output.answer.strip()
        parts = (
            [general, messages_for().chat_referral] if general else [messages_for().chat_referral]
        )
        return "\n\n".join(parts), "referral"
    return output.answer.strip(), "answer"


def _references(found: NewText) -> str:
    """Name the texts found, the way a reader cites them: surah and ayah, book and number."""
    texts = messages_for()
    named: list[str] = []
    if found.verse is not None:
        named.append(
            texts.chat_verse_reference.format(surah=found.verse.surah_name, ayah=found.verse.ayah)
        )
    if found.hadith is not None:
        named.append(
            texts.chat_hadith_reference.format(
                book=found.hadith.collection.name_ar, number=found.hadith.number
            )
        )
    return texts.chat_reference_joiner.join(named)


async def _give_back(db: AsyncSession, row: ChatMessage, log: CallLog, insight_id: int) -> None:
    """Free the slot of a message that got no answer; the call is still recorded."""
    await db.delete(row)
    db.add_all(call_rows(log.records, insight_id=insight_id))
    await db.commit()
