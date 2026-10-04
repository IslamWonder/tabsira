"""
An insight as its owner sees it: every text of scripture read from the store by reference.

Nothing a model wrote is ever shown as Quran or hadith. The verse and the
hadith come from the scripture read API's own readers (exact text, hash,
spans, quranpedia link, «تحقق في الدرر» link, the editor's dorar.net ruling).
A hadith is shown only when its ruling in force is صحيح or حسن (decision 18);
without a ruling the insight says it waits for verification and shows the
verse alone; with any other ruling it is not shown at all. A small step that
rests on a text that is not shown is not shown either.

Rendering to the owner is recorded: `describe` writes a `shown` exposure the first
time each text of the insight reaches its owner (v2 §11, masar §10.5), unless memory
is off. A stranger's reading of a public insight records nothing.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.config import Settings
from src.messages import messages_for
from src.models import ChatMessage, ChatStatus, Insight, LearningUnit, Scan
from src.owner import Owner
from src.pipeline.engine import HadithRef, QuranRef, RelationType
from src.pipeline.schemas import BBox
from src.routers.scripture import HadithOut, QuranVerseOut, read_hadith, read_verse
from src.schemas.insight import (
    ActionOut,
    ChatMessageOut,
    ChatOut,
    EvidenceWhy,
    ExplanationOut,
    InsightDetailOut,
    InsightHadith,
    InsightImageOut,
    InsightQuran,
    InsightWhyOut,
    LearningUnitOut,
    PublicHadith,
    PublicQuran,
    StepOut,
)
from src.services import learner_service
from src.storage.sounds import ENTITY_ID


def action_means(state: str) -> str:
    """Return what the learner's answer to the small step means: a declaration, never a proof."""
    texts = messages_for()
    return {"done": texts.action_done_means, "later": texts.action_later_means}[state]


def evidence_why(evidence: dict[str, Any] | None) -> EvidenceWhy | None:
    if not evidence:
        return None
    relation = RelationType(evidence["relation"])
    return EvidenceWhy(
        relation=relation,
        relation_label=messages_for().relation_labels[relation.value],
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


# A learning unit a part may rest on; whether it exists was checked when the insight was kept.
UNIT_REFERENCE = re.compile(r"masar:T[0-9]{2}_[0-9]{2}")


def shown_ids(verse: QuranVerseOut | None, hadith: HadithOut | None) -> set[str]:
    """Return the evidence ids (`quran:30:50`, `hadith:bukhari:1032`) of the texts shown."""
    shown = set()
    if verse is not None:
        shown.add(f"quran:{verse.surah}:{verse.ayah}")
    if hadith is not None:
        shown.add(f"hadith:{hadith.collection.slug}:{hadith.number}")
    return shown


def rests_on_hidden(refs: list[str], shown: set[str]) -> bool:
    """Tell whether any reference is not a text shown here or a learning unit: unknown is hidden."""
    return any(ref not in shown and not UNIT_REFERENCE.fullmatch(ref) for ref in refs)


def visible_parts(parts: list[dict[str, Any]], shown: set[str]) -> list[dict[str, Any]]:
    """
    Return the explanation parts that may show beside the texts in `shown`.

    What the verse or the hadith adds is said only beside it, and a part that rests on a text
    not shown (a hadith whose ruling is missing or no longer eligible) waits with it.
    """
    absent = {"quran"} if not any(ref.startswith("quran:") for ref in shown) else set()
    absent |= {"sunnah"} if not any(ref.startswith("hadith:") for ref in shown) else set()
    return [
        part
        for part in parts
        if part["section"] not in absent
        and not rests_on_hidden([str(ref) for ref in part.get("sources", [])], shown)
    ]


def visible_step(step: dict[str, Any] | None, shown: set[str]) -> dict[str, Any] | None:
    """Return the small step unless it rests on a text that is not shown."""
    if not step:
        return None
    grounded = [str(ref) for ref in step.get("grounded_in", [])]
    return None if rests_on_hidden(grounded, shown) else step


def explanation_out(
    parts: list[dict[str, Any]], verse: QuranVerseOut | None, hadith: HadithOut | None
) -> list[ExplanationOut]:
    """
    Return the explanation parts that may show next to the texts shown.

    What the verse or the hadith adds is said only beside it, and a part that
    rests on a text not shown (a hadith waiting for its ruling) waits with it.
    """
    return [
        ExplanationOut(
            section=part["section"],
            label=messages_for().explanation_labels[part["section"]],
            text=part["text"],
        )
        for part in visible_parts(parts, shown_ids(verse, hadith))
    ]


def step_out(
    step: dict[str, Any] | None, verse: QuranVerseOut | None, hadith: HadithOut | None
) -> StepOut | None:
    """
    Return the small step, or None when it rests on a text that is not shown.

    It is «من السنة» only when it is a practice the text grounds
    (`text_grounded`) and rests on a hadith shown with it (v2 §14, masar
    §11.3); anything else is «اقتراح عملي».
    """
    step = visible_step(step, shown_ids(verse, hadith))
    if step is None:
        return None
    grounded = [str(ref) for ref in step.get("grounded_in", [])]
    from_sunnah = step["kind"] == "text_grounded" and any(
        ref.startswith("hadith:") for ref in grounded
    )
    return StepOut(
        text=str(step["text"]),
        kind=step["kind"],
        label=messages_for().step_from_sunnah if from_sunnah else messages_for().step_suggestion,
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


def answer_is_shown(row: ChatMessage, shown: set[str]) -> bool:
    """Tell whether every text an answer was written beside is still shown; unknown is not."""
    return row.evidence_ids is not None and set(row.evidence_ids) <= shown


# An evidence id as the chat keeps it: `quran:30:50` or `hadith:bukhari:1032`.
EVIDENCE_ID = re.compile(
    r"^(?:quran:(?P<surah>[0-9]+):(?P<ayah>[0-9]+)|hadith:(?P<book>[^:]+):(?P<number>[^:]+))$"
)


async def found_texts(
    db: AsyncSession, row: ChatMessage, shown: set[str]
) -> tuple[QuranVerseOut | None, HadithOut | None] | None:
    """
    Read the texts an answer found by itself (a request for another text, v2 §14).

    They are the evidence ids of the row that the insight does not show, read from the
    store by id; a hadith shows only while its ruling is eligible. None when any of them
    is not in the store or not eligible: the answer is then no longer shown.
    """
    verse: QuranVerseOut | None = None
    hadith: HadithOut | None = None
    for ref in row.evidence_ids or []:
        match = EVIDENCE_ID.match(ref)
        if ref in shown or match is None:
            continue
        if match.group("surah") is not None:
            verse = await read_verse(db, int(match.group("surah")), int(match.group("ayah")))
            if verse is None:
                return None
        else:
            hadith = await read_hadith(db, match.group("book"), match.group("number"))
            if hadith is None or not hadith.eligible:
                return None
    return verse, hadith


async def chat_of(
    db: AsyncSession,
    settings: Settings,
    insight: Insight,
    verse: QuranVerseOut | None,
    hadith: HadithOut | None,
) -> ChatOut:
    shown = shown_ids(verse, hadith)
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
        messages=[await message_out(db, row, shown) for row in rows],
    )


async def message_out(db: AsyncSession, row: ChatMessage, shown: set[str]) -> ChatMessageOut:
    """
    Return the message; a note stands in place of an answer no longer shown.

    An answer is shown while every text it was written beside is: the insight's texts in
    `shown`, and the text it found itself, read from the store beside it.
    """
    texts = messages_for()
    found = await found_texts(db, row, shown)
    verse, hadith = found if found is not None else (None, None)
    withdrawn = found is None or not answer_is_shown(row, shown | shown_ids(verse, hadith))
    return ChatMessageOut.model_validate(
        {
            "question": row.question,
            "answer": texts.chat_answer_withdrawn if withdrawn else row.answer,
            "level": row.level,
            "kind": row.kind,
            "answered_at": row.answered_at,
            "quran": PublicQuran(tag=texts.quran_tag, verse=verse)
            if verse is not None and not withdrawn
            else None,
            "hadith": PublicHadith(tag=texts.sunnah_tag, hadith=hadith)
            if hadith is not None and not withdrawn
            else None,
        }
    )


def label_of(insight: Insight) -> str | None:
    if insight.engine == "prepared":
        return messages_for().prepared_example
    if insight.engine == "demo":
        return messages_for().demo_engine
    return None


def shown_fields(
    insight: Insight,
    verse: QuranVerseOut | None,
    hadith: HadithOut | None,
    awaiting: bool,
    *,
    public: bool = False,
) -> dict[str, Any]:
    """
    Return the fields every reader sees alike, owner or stranger, from what the store shows.

    One place for the hidden-hadith rules (status, notice, the parts and the step that rest on a
    text not shown), so the owner's view and the public view cannot drift apart. A public reader
    gets the texts without «لماذا ظهر هذا؟» (`why`, which can come from the photo or the
    profile) and without the «ما ظهر» part, which describes the photo.
    """
    texts = messages_for()
    explanation = explanation_out(insight.explanation, verse, hadith)
    quran: Any = None
    sunnah: Any = None
    if verse:
        quran = (
            PublicQuran(tag=texts.quran_tag, verse=verse)
            if public
            else InsightQuran(
                tag=texts.quran_tag, verse=verse, why=evidence_why(insight.quran_evidence)
            )
        )
    if hadith:
        sunnah = (
            PublicHadith(tag=texts.sunnah_tag, hadith=hadith)
            if public
            else InsightHadith(
                tag=texts.sunnah_tag, hadith=hadith, why=evidence_why(insight.hadith_evidence)
            )
        )
    return {
        "quran": quran,
        "hadith": sunnah,
        "hadith_status": "shown" if hadith else "awaiting_verification" if awaiting else "none",
        "notice": texts.hadith_awaits_verification if awaiting else None,
        "pair_complete": verse is not None and hadith is not None,
        "explanation_tag": texts.explanation_tag,
        "explanation": [p for p in explanation if p.section != "seen"] if public else explanation,
        "small_step": step_out(insight.small_step, verse, hadith),
    }


async def record_display(
    db: AsyncSession,
    owner: Owner,
    insight: Insight,
    verse: QuranVerseOut | None,
    hadith: HadithOut | None,
) -> None:
    """Write the `shown` exposure of the texts rendered now, once per insight and text."""
    written = await learner_service.record_shown(
        db,
        owner,
        insight_id=insight.id,
        at=clock.utcnow(),
        quran=QuranRef(surah=verse.surah, ayah=verse.ayah) if verse else None,
        hadith=HadithRef(collection=hadith.collection.slug, number=hadith.number)
        if hadith
        else None,
        concept=str(insight.why.get("concept") or "") or None,
        unit_id=insight.learning_unit_id,
    )
    if written:
        await db.commit()


def sound_path(insight: Insight) -> str | None:
    """Return the API path of the sound of the first ontology entity the insight rests on."""
    for entity_id in insight.why.get("ontology_entity_ids", []):
        if isinstance(entity_id, str) and ENTITY_ID.fullmatch(entity_id):
            return f"/sounds/ontology/{entity_id}"
    return None


async def describe(
    db: AsyncSession, settings: Settings, insight: Insight, owner: Owner
) -> InsightDetailOut:
    """Return the owner's insight, its scripture hydrated from the store, and record the display."""
    verse, hadith, awaiting = await shown_evidence(db, insight)
    await record_display(db, owner, insight, verse, hadith)
    scan = await db.get(Scan, insight.scan_id) if insight.scan_id is not None else None
    sensitive = bool(scan and scan.sensitive)
    return InsightDetailOut(
        id=insight.id,
        scan_id=insight.scan_id,
        origin=insight.origin,
        engine=insight.engine,
        label=label_of(insight),
        title=insight.title,
        glimpse=insight.glimpse,
        anchor=BBox.model_validate(insight.anchor) if insight.anchor else None,
        relation=RelationType(insight.relation),
        relation_label=messages_for().relation_labels[insight.relation],
        sound_url=sound_path(insight),
        **shown_fields(insight, verse, hadith, awaiting),
        why=InsightWhyOut(
            visible_clues=list(insight.why.get("visible_clues", [])),
            concept=str(insight.why.get("concept", "")),
            limits=list(insight.why.get("limits", [])),
            personalised_because=insight.why.get("personalised_because"),
        ),
        learning_unit=await _unit(db, insight),
        action=ActionOut(
            state=insight.action_state,
            at=insight.action_at,
            means=action_means(insight.action_state.value) if insight.action_state else None,
        ),
        chat=await chat_of(db, settings, insight, verse, hadith),
        image=InsightImageOut(
            sensitive=sensitive,
            url=f"/scans/{scan.id}/image" if scan is not None and not sensitive else None,
        ),
        completed_at=insight.completed_at,
        place_id=insight.place_id,
        published_at=insight.published_at,
        created_at=insight.created_at,
        disclosure=messages_for().ai_disclosure,
    )
