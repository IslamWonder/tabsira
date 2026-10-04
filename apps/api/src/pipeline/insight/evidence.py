"""
The evidence gate: which found texts may stand behind an insight, and which one does.

Step one is eligibility and relevance, never traded for anything else (masar
§10.3, v2 §11):

- a verse is eligible: the store holds it exactly as quranpedia gives it;
- a hadith is eligible only when its latest dorar.net ruling, recorded by an
  editor, is صحيح or حسن (decision 18, `rulings.is_eligible`). A hadith the
  insight wanted that has no ruling yet is queued for an editor, ordered by
  demand, and listed in `awaiting_ruling`; the insight then carries its verse
  alone, never a weaker or distant hadith in its place;
- relevance is judged by the verifier (a chat model, structured output): for
  each text, whether its own meaning carries the concept, how strongly, and
  how it relates to the scene. Texts are labelled Q1, H1 ...: the model never
  handles a stored id, and never writes a text.

Step two ranks among what passed: the strongest tier first; inside it, a text
the learner has not seen comes before one they have (diversity, v2 §11); when
every text of that tier was seen, the best one is shown again as a review,
never a weaker one; the reranker's order breaks the remaining ties.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.config import AiStage
from src.models import Hadith, QuranVerse
from src.pipeline.engine import HadithRef, LearnerContext, QuranRef, RelationType
from src.pipeline.insight.guard import EngineGuard
from src.pipeline.insight.planner import PlannedCandidate, RelationName
from src.pipeline.insight.search import Found
from src.pipeline.leak_guard import ScriptureLeakError
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import SceneAnalysis
from src.scripture import rulings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = "insight_verifier_system.v1"
MAX_OUTPUT_TOKENS = 4096
# Texts of each corpus shown to the verifier per candidate, and their length.
SHORTLIST = 4
TEXT_CHARS = 700
STRENGTH_ORDER = {"strong": 0, "medium": 1, "weak": 2}
RELATION_ORDER = {relation: rank for rank, relation in enumerate(RelationType)}


class TextVerdict(BaseModel):
    label: Annotated[str, Field(description="Q1, Q2 ... or H1, H2 ... as given.")]
    relevant: bool
    strength: Literal["strong", "medium", "weak"]
    relation: RelationName
    limit: Annotated[str, Field(description="Arabic: what the text does not allow saying.")]


class CandidateVerdict(BaseModel):
    candidate: int
    texts: list[TextVerdict]


class VerifierOutput(BaseModel):
    candidates: list[CandidateVerdict]


@dataclass(frozen=True, slots=True)
class Shortlist:
    """What one candidate's searches found, as the verifier will see it."""

    candidate: PlannedCandidate
    quran: list[Found]
    hadith: list[Found]

    def labelled(self) -> dict[str, Found]:
        return {f"Q{i}": item for i, item in enumerate(self.quran, start=1)} | {
            f"H{i}": item for i, item in enumerate(self.hadith, start=1)
        }


@dataclass(frozen=True, slots=True)
class Chosen:
    """The text behind one half of an insight, and why it was chosen."""

    found: Found
    relation: RelationType
    limit: str
    review: bool
    unseen_preferred: bool
    strength: str = "strong"


@dataclass
class GateResult:
    """What the gate decided for one candidate."""

    candidate: PlannedCandidate
    quran: Chosen | None = None
    hadith: Chosen | None = None
    quran_ref: QuranRef | None = None
    hadith_ref: HadithRef | None = None
    # The hadith it wanted that waits for an editor's ruling.
    awaiting: list[HadithRef] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.quran is not None or self.hadith is not None

    @property
    def relation(self) -> RelationType:
        """
        The weaker of the planned relation and the main text's own relation to the scene.

        A main text the verifier called weak (a general or remote link) makes a general
        reminder, whatever relation was claimed for it.
        """
        main = self.quran or self.hadith
        if main is None or main.strength == "weak":
            return RelationType.THEMATIC_REMINDER
        return max(self.candidate.relation, main.relation, key=RELATION_ORDER.__getitem__)


def verifier_message(scene: SceneAnalysis, shortlists: Sequence[Shortlist]) -> str:
    payload: dict[str, Any] = {
        "scene": {
            "description": scene.description,
            "entities": [entity.label_arabic for entity in scene.entities],
            "actions": [action.label for action in scene.actions],
        },
        "candidates": [
            {
                "candidate": index,
                "concept": item.candidate.concept,
                "value": item.candidate.value,
                "relation": item.candidate.relation.value,
                "texts": [
                    {"label": label, "text": found.document.text[:TEXT_CHARS]}
                    for label, found in item.labelled().items()
                ],
            }
            for index, item in enumerate(shortlists)
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


async def verify(
    client: ModelClient,
    scene: SceneAnalysis,
    shortlists: Sequence[Shortlist],
    guard: EngineGuard,
    *,
    attempts: int = 2,
) -> dict[int, dict[str, TextVerdict]]:
    """
    Return, per candidate index, the verdict on each label.

    Each candidate is judged in a call of its own and the calls run together: a
    verdict never depends on another candidate, and one long answer took as long
    as several short ones side by side. The first error of any call is raised.
    """
    judged = await asyncio.gather(
        *(_verify_one(client, scene, shortlist, guard, attempts) for shortlist in shortlists),
        return_exceptions=True,
    )
    for outcome in judged:
        if isinstance(outcome, BaseException):
            raise outcome
    return {index: verdicts for index, verdicts in enumerate(judged) if isinstance(verdicts, dict)}


async def _verify_one(
    client: ModelClient,
    scene: SceneAnalysis,
    shortlist: Shortlist,
    guard: EngineGuard,
    attempts: int,
) -> dict[str, TextVerdict]:
    """Judge one candidate's texts; an answer whose limits leak is asked again, then dropped."""
    system = load_prompt(SYSTEM_PROMPT)
    user = verifier_message(scene, [shortlist])
    known = shortlist.labelled()
    for attempt in range(1, attempts + 1):
        result = await client.chat_json(
            VerifierOutput,
            stage=AiStage.VERIFY,
            system=system.text,
            user=user,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        mine = [item for item in result.value.candidates if item.candidate == 0]
        limits = {
            f"candidates.{c.candidate}.{t.label}.limit": t.limit
            for c in result.value.candidates
            for t in c.texts
            if t.limit.strip()
        }
        try:
            await guard.ensure_clean(limits)
        except ScriptureLeakError as error:
            log.warning("verifier answer refused (attempt %d): %s", attempt, error)
            continue
        return {t.label: t for item in mine for t in item.texts if t.label in known}
    # Still leaking: this candidate gets no verdict, so none of its texts passes the
    # gate; the others are judged in their own calls and go on.
    return {}


def _ordered(
    labelled: dict[str, Found], verdicts: dict[str, TextVerdict], prefix: str
) -> list[tuple[Found, TextVerdict]]:
    """Return the relevant texts of one corpus, strongest first, the search order breaking ties."""
    relevant = [
        (found, verdicts[label])
        for label, found in labelled.items()
        if label.startswith(prefix) and label in verdicts and verdicts[label].relevant
    ]
    # A stable sort keeps the search order inside each strength.
    return sorted(relevant, key=lambda pair: STRENGTH_ORDER[pair[1].strength])


def pick(ranked: Sequence[tuple[Found, TextVerdict]], seen: frozenset[int]) -> Chosen | None:
    """Pick from the strongest tier: an unseen text first, else the best one as a review."""
    if not ranked:
        return None
    top = STRENGTH_ORDER[ranked[0][1].strength]
    tier = [pair for pair in ranked if STRENGTH_ORDER[pair[1].strength] == top]
    unseen = [pair for pair in tier if pair[0].key not in seen]
    found, verdict = (unseen or tier)[0]
    return Chosen(
        found=found,
        relation=RelationType(verdict.relation),
        limit=verdict.limit.strip(),
        review=not unseen,
        unseen_preferred=bool(unseen) and unseen[0] is not tier[0],
        strength=verdict.strength,
    )


async def seen_ids(
    session: AsyncSession, learner: LearnerContext
) -> tuple[frozenset[int], frozenset[int]]:
    """Return the ids of the verses and hadiths the learner saw; none when personalisation is off."""
    if not learner.personalization_enabled:
        return frozenset(), frozenset()
    verses: frozenset[int] = frozenset()
    hadiths: frozenset[int] = frozenset()
    if learner.seen_quran:
        pairs = [(ref.surah, ref.ayah) for ref in learner.seen_quran]
        verses = frozenset(
            await session.scalars(
                select(QuranVerse.id).where(tuple_(QuranVerse.surah, QuranVerse.ayah).in_(pairs))
            )
        )
    if learner.seen_hadith:
        keys = [(ref.collection, ref.number) for ref in learner.seen_hadith]
        hadiths = frozenset(
            await session.scalars(
                select(Hadith.id).where(tuple_(Hadith.collection, Hadith.number).in_(keys))
            )
        )
    return verses, hadiths


async def quran_ref(session: AsyncSession, verse_id: int) -> QuranRef:
    row = (
        await session.execute(
            select(QuranVerse.surah, QuranVerse.ayah).where(QuranVerse.id == verse_id)
        )
    ).one()
    return QuranRef(surah=row.surah, ayah=row.ayah)


async def hadith_ref(session: AsyncSession, hadith_id: int) -> HadithRef:
    row = (
        await session.execute(
            select(Hadith.collection, Hadith.number).where(Hadith.id == hadith_id)
        )
    ).one()
    return HadithRef(collection=row.collection, number=row.number)


async def gate(
    session: AsyncSession,
    shortlist: Shortlist,
    verdicts: dict[str, TextVerdict],
    *,
    seen_verses: frozenset[int],
    seen_hadiths: frozenset[int],
) -> GateResult:
    """Apply eligibility, then relevance, then the learner's history to one candidate."""
    labelled = shortlist.labelled()
    result = GateResult(shortlist.candidate)
    result.quran = pick(_ordered(labelled, verdicts, "Q"), seen_verses)
    hadiths = _ordered(labelled, verdicts, "H")
    if hadiths:
        top = STRENGTH_ORDER[hadiths[0][1].strength]
        tier = [pair for pair in hadiths if STRENGTH_ORDER[pair[1].strength] == top]
        eligible = [pair for pair in tier if await rulings.is_eligible(session, pair[0].key)]
        wanted = tier[0][0]
        unruled = not any(pair[0] is wanted for pair in eligible) and (
            await rulings.enqueue_demand(session, wanted.key)
        )
        if unruled:
            # Decision 18: the best hadith waits for an editor's ruling, in demand order,
            # and until then the insight shows its verse alone, never another hadith.
            result.awaiting.append(await hadith_ref(session, wanted.key))
        else:
            result.hadith = pick(eligible, seen_hadiths)
    _drop_remote_companion(result)
    if result.quran is not None:
        result.quran_ref = await quran_ref(session, result.quran.found.key)
    if result.hadith is not None:
        result.hadith_ref = await hadith_ref(session, result.hadith.found.key)
    return result


def _drop_remote_companion(result: GateResult) -> None:
    """Drop a companion text the verifier called remote (v2 §11); the verse stays."""
    if result.quran is None or result.hadith is None:
        return
    if result.hadith.strength == "weak":
        result.hadith = None
    elif result.quran.strength == "weak":
        result.quran = None


def shortlist_of(
    candidate: PlannedCandidate, quran: Sequence[Found], hadith: Sequence[Found]
) -> Shortlist:
    return Shortlist(candidate, list(quran[:SHORTLIST]), list(hadith[:SHORTLIST]))
