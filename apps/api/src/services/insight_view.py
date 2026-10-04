"""
An insight as its owner sees it: every text of scripture read from the store by reference.

Nothing a model wrote is ever shown as Quran or hadith. The verse and the
hadith come from the scripture read API's own readers (exact text, hash,
spans, quranpedia link, «تحقق في الدرر» link, the editor's dorar.net ruling).
A hadith is shown only when its ruling in force is صحيح or حسن (decision 18);
without a ruling the insight says it waits for verification and shows the
verse alone; with any other ruling it is not shown at all. A small step that
rests on a text that is not shown is not shown either.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import messages
from src.config import Settings
from src.models import ChatMessage, ChatStatus, Insight, LearningUnit, Scan
from src.pipeline.engine import RelationType
from src.pipeline.schemas import BBox
from src.routers.scripture import HadithOut, QuranVerseOut, read_hadith, read_verse
from src.schemas.insight import (
    ActionOut,
    ChatMessageOut,
    ChatOut,
    EvidenceWhy,
    ExplanationOut,
    InsightHadith,
    InsightImageOut,
    InsightOut,
    InsightQuran,
    LearningUnitOut,
    StepOut,
    WhyOut,
)

ACTION_MEANS = {"done": messages.ACTION_DONE_MEANS, "later": messages.ACTION_LATER_MEANS}


def evidence_why(evidence: dict[str, Any] | None) -> EvidenceWhy | None:
    if not evidence:
        return None
    relation = RelationType(evidence["relation"])
    return EvidenceWhy(
        relation=relation,
        relation_label=messages.RELATION_LABELS[relation.value],
        matched_on=str(evidence.get("matched_on", "")),
    )


async def evidence(
    db: AsyncSession, quran: tuple[int, int] | None, hadith: tuple[str, str] | None
) -> tuple[QuranVerseOut | None, HadithOut | None, bool]:
    """Return the verse and the hadith to show, and whether the hadith waits for its ruling."""
    verse = await read_verse(db, *quran) if quran is not None else None
    shown = None
    awaiting = False
    if hadith is not None:
        found = await read_hadith(db, *hadith)
        if found is not None and found.eligible:
            shown = found
        elif found is not None and found.ruling is None:
            awaiting = True
    return verse, shown, awaiting


async def shown_evidence(
    db: AsyncSession, insight: Insight
) -> tuple[QuranVerseOut | None, HadithOut | None, bool]:
    """Return what `evidence` returns for the references an insight keeps."""
    quran = (
        (insight.quran_surah, insight.quran_ayah)
        if insight.quran_surah is not None and insight.quran_ayah is not None
        else None
    )
    hadith = (
        (insight.hadith_collection, insight.hadith_number)
        if insight.hadith_collection is not None and insight.hadith_number is not None
        else None
    )
    return await evidence(db, quran, hadith)


EVIDENCE_PREFIXES = ("quran:", "hadith:")


def shown_ids(verse: QuranVerseOut | None, hadith: HadithOut | None) -> set[str]:
    """Return the evidence ids (`quran:30:50`, `hadith:bukhari:1032`) of the texts shown."""
    shown = set()
    if verse is not None:
        shown.add(f"quran:{verse.surah}:{verse.ayah}")
    if hadith is not None:
        shown.add(f"hadith:{hadith.collection.slug}:{hadith.number}")
    return shown


def _rests_on_hidden(refs: list[str], shown: set[str]) -> bool:
    return any(ref.startswith(EVIDENCE_PREFIXES) and ref not in shown for ref in refs)


def explanation_out(
    parts: list[dict[str, Any]], verse: QuranVerseOut | None, hadith: HadithOut | None
) -> list[ExplanationOut]:
    """
    Return the explanation parts that may show next to the texts shown.

    What the verse or the hadith adds is said only beside it, and a part that
    rests on a text not shown (a hadith waiting for its ruling) waits with it.
    """
    shown = shown_ids(verse, hadith)
    absent = {"quran"} if verse is None else set()
    absent |= {"sunnah"} if hadith is None else set()
    return [
        ExplanationOut(
            section=part["section"],
            label=messages.EXPLANATION_LABELS[part["section"]],
            text=part["text"],
        )
        for part in parts
        if part["section"] not in absent
        and not _rests_on_hidden([str(ref) for ref in part.get("sources", [])], shown)
    ]


def step_out(
    step: dict[str, Any] | None, verse: QuranVerseOut | None, hadith: HadithOut | None
) -> StepOut | None:
    """
    Return the small step, or None when it rests on a text that is not shown.

    It is «من السنة» only when it rests on a hadith shown with it (v2 §14);
    anything else is «اقتراح عملي».
    """
    if not step:
        return None
    shown = shown_ids(verse, hadith)
    grounded = [str(ref) for ref in step.get("grounded_in", [])]
    if _rests_on_hidden(grounded, shown):
        return None
    from_sunnah = any(ref.startswith("hadith:") for ref in grounded)
    return StepOut(
        text=str(step["text"]),
        kind=step["kind"],
        label=messages.STEP_FROM_SUNNAH if from_sunnah else messages.STEP_SUGGESTION,
    )


async def _unit(db: AsyncSession, insight: Insight) -> LearningUnitOut | None:
    if insight.learning_unit_id is None or insight.learning_path_version is None:
        return None
    unit = await db.get(LearningUnit, (insight.learning_path_version, insight.learning_unit_id))
    if unit is None:
        return None
    return LearningUnitOut(
        id=unit.id, title=unit.title, domain_id=unit.domain_id, path_version=unit.path_version
    )


async def chat_of(db: AsyncSession, settings: Settings, insight: Insight) -> ChatOut:
    rows = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.insight_id == insight.id, ChatMessage.status == ChatStatus.ANSWERED)
            .order_by(ChatMessage.id)
        )
    ).all()
    limit = settings.max_chat_user_messages
    return ChatOut(
        enabled=settings.feature_chat,
        used=len(rows),
        limit=limit,
        remaining=max(limit - len(rows), 0),
        messages=[message_out(row) for row in rows],
    )


def message_out(row: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut.model_validate(
        {
            "question": row.question,
            "answer": row.answer,
            "level": row.level,
            "kind": row.kind,
            "answered_at": row.answered_at,
        }
    )


def _label(insight: Insight) -> str | None:
    if insight.engine == "prepared":
        return messages.PREPARED_EXAMPLE
    if insight.engine == "demo":
        return messages.DEMO_ENGINE
    return None


async def describe(db: AsyncSession, settings: Settings, insight: Insight) -> InsightOut:
    """Return the owner's insight, its scripture hydrated from the store."""
    verse, hadith, awaiting = await shown_evidence(db, insight)
    scan = await db.get(Scan, insight.scan_id) if insight.scan_id is not None else None
    sensitive = bool(scan and scan.sensitive)
    return InsightOut(
        id=insight.id,
        scan_id=insight.scan_id,
        origin=insight.origin,
        engine=insight.engine,
        label=_label(insight),
        title=insight.title,
        glimpse=insight.glimpse,
        anchor=BBox.model_validate(insight.anchor) if insight.anchor else None,
        relation=RelationType(insight.relation),
        relation_label=messages.RELATION_LABELS[insight.relation],
        quran=InsightQuran(
            tag=messages.QURAN_TAG, verse=verse, why=evidence_why(insight.quran_evidence)
        )
        if verse
        else None,
        hadith=InsightHadith(
            tag=messages.SUNNAH_TAG, hadith=hadith, why=evidence_why(insight.hadith_evidence)
        )
        if hadith
        else None,
        hadith_status="shown" if hadith else "awaiting_verification" if awaiting else "none",
        notice=messages.HADITH_AWAITS_VERIFICATION if awaiting else None,
        pair_complete=verse is not None and hadith is not None,
        explanation_tag=messages.EXPLANATION_TAG,
        explanation=explanation_out(insight.explanation, verse, hadith),
        why=WhyOut(
            visible_clues=list(insight.why.get("visible_clues", [])),
            concept=str(insight.why.get("concept", "")),
            limits=list(insight.why.get("limits", [])),
            personalised_because=insight.why.get("personalised_because"),
        ),
        small_step=step_out(insight.small_step, verse, hadith),
        learning_unit=await _unit(db, insight),
        action=ActionOut(
            state=insight.action_state,
            at=insight.action_at,
            means=ACTION_MEANS[insight.action_state.value] if insight.action_state else None,
        ),
        chat=await chat_of(db, settings, insight),
        image=InsightImageOut(
            sensitive=sensitive,
            url=f"/scans/{scan.id}/image" if scan is not None and not sensitive else None,
        ),
        completed_at=insight.completed_at,
        place_id=insight.place_id,
        created_at=insight.created_at,
        disclosure=messages.AI_DISCLOSURE,
    )
