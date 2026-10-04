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
CHAT_LIMIT_REACHED.

The model writes the level of the question (v2 §12) before its answer. A
request for another text is answered by the app itself: it needs a new
search, and no text is ever quoted from memory. A personal case (level د) gets
general information and the app's referral. Every answer goes through the leak
guard, with the insight's own texts as a corpus, and carries the disclosure.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Literal

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
from src.pipeline.leak_guard import LeakGuard, PatternLeakDetector, ShingleOverlapDetector
from src.pipeline.prompt import load_prompt
from src.routers.scripture import HadithOut, QuranVerseOut
from src.scans.workflow import call_rows
from src.schemas.insight import ChatReply
from src.scripture.overlap import repeats_store
from src.services.insight_view import explanation_out, message_out, shown_evidence, step_out

SYSTEM_PROMPT = "insight_chat_system.v2"
USER_PROMPT = "insight_chat_user.v2"
MAX_OUTPUT_TOKENS = 1200
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
    answer: Annotated[
        str, Field(description="Arabic, at most 120 words; empty when asks_for_new_text")
    ]


def _refused(code: ErrorCode, detail: str, status_code: int) -> AppError:
    return AppError(code, detail, status_code=status_code)


async def _reserve(
    db: AsyncSession, settings: Settings, insight: Insight, key: str, question: str
) -> ChatMessage:
    """Hold a slot for one message, or return the answered message of the same key."""
    await db.scalar(select(Insight.id).where(Insight.id == insight.id).with_for_update())
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


async def _history(db: AsyncSession, insight: Insight) -> str:
    rows = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.insight_id == insight.id, ChatMessage.status == ChatStatus.ANSWERED)
            .order_by(ChatMessage.id)
        )
    ).all()
    if not rows:
        return "(none)"
    return "\n".join(f"- Q: {row.question}\n  A: {row.answer}" for row in rows)


async def _cited_texts(db: AsyncSession, insight: Insight) -> list[str]:
    """
    Return the stored texts the insight cites, shown or not, as the leak guard's corpus.

    A hadith hidden for its ruling (none yet, or not صحيح or حسن) is guarded
    against all the same: the model must not quote it either.
    """
    texts: list[str | None] = []
    if insight.quran_surah is not None and insight.quran_ayah is not None:
        texts.append(
            await db.scalar(
                select(QuranVerse.text).where(
                    QuranVerse.surah == insight.quran_surah, QuranVerse.ayah == insight.quran_ayah
                )
            )
        )
    if insight.hadith_collection is not None and insight.hadith_number is not None:
        texts.append(
            await db.scalar(
                select(Hadith.text).where(
                    Hadith.collection == insight.hadith_collection,
                    Hadith.number == insight.hadith_number,
                )
            )
        )
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
    return "\n".join(f"- {part.section}: {part.text}" for part in parts) or "(none)"


def _step(verse: QuranVerseOut | None, hadith: HadithOut | None, insight: Insight) -> str:
    step = step_out(insight.small_step, verse, hadith)
    return f"- {step.label}: {step.text}" if step is not None else "(none)"


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
) -> ChatReply:
    """Answer one message of the insight's chat, or replay the answer of its key."""
    question = question.strip()
    row = await _reserve(db, settings, insight, key, question)
    if row.status is ChatStatus.PENDING:
        await _answer(db, settings, insight, row, client_factory)
    used = await _used(db, insight)
    limit = settings.max_chat_user_messages
    return ChatReply(
        message=message_out(row),
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
) -> None:
    verse, hadith, _awaiting = await shown_evidence(db, insight)
    references: list[str] = []
    corpus = await _cited_texts(db, insight)
    if verse is not None:
        references.append(f"{verse.surah_name} {verse.surah}:{verse.ayah}")
    if hadith is not None:
        references.append(f"{hadith.collection.name_ar} {hadith.number}")
    user = load_prompt(USER_PROMPT).render(
        title=insight.title,
        glimpse=insight.glimpse,
        relation=insight.relation,
        references="; ".join(references) or "(none)",
        explanation=_explanation(verse, hadith, insight),
        why=_why(insight),
        step=_step(verse, hadith, insight),
        history=await _history(db, insight),
        question=row.question,
    )
    log = CallLog()
    client = client_factory(log)
    try:
        result = await client.chat_json(
            ChatModelOutput,
            stage=AiStage.CHAT,
            system=load_prompt(SYSTEM_PROMPT).render(shown_texts=_shown_texts(verse, hadith)),
            user=user,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except AiCallError:
        await _give_back(db, row, log, insight.id)
        raise _refused(ErrorCode.MODEL_UNAVAILABLE, "The chat model did not answer.", 503) from None
    output = result.value
    text, kind = _compose(output)
    guard = LeakGuard([PatternLeakDetector(), ShingleOverlapDetector(corpus)])
    leaked = kind != "new_search" and (
        guard.check(output.answer).leaked or await repeats_store(db, [output.answer])
    )
    if not text.strip() or leaked:
        await _give_back(db, row, log, insight.id)
        raise _refused(ErrorCode.CHAT_ANSWER_REJECTED, "The answer was refused.", 502)
    row.status = ChatStatus.ANSWERED
    row.answer = text
    row.level = output.level
    row.kind = kind
    row.answered_at = clock.utcnow()
    db.add_all(call_rows(log.records, insight_id=insight.id))
    await db.commit()


def _compose(output: ChatModelOutput) -> tuple[str, str]:
    """Return the text shown and its kind: the app's own words for a new text, a referral for د."""
    if output.asks_for_new_text:
        return messages_for().chat_needs_new_search, "new_search"
    if output.level == "d":
        general = output.answer.strip()
        parts = (
            [general, messages_for().chat_referral] if general else [messages_for().chat_referral]
        )
        return "\n\n".join(parts), "referral"
    return output.answer.strip(), "answer"


async def _give_back(db: AsyncSession, row: ChatMessage, log: CallLog, insight_id: int) -> None:
    """Free the slot of a message that got no answer; the call is still recorded."""
    await db.delete(row)
    db.add_all(call_rows(log.records, insight_id=insight_id))
    await db.commit()
