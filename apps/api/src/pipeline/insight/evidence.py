"""
The evidence relevance verifier and the gate: which found texts may stand behind an insight.

Three things are kept apart and none stands in for another (the brief of
2026-10-05, §1):

- relevance to the intent, judged by `EvidenceRelevanceVerifier` (a chat
  model, structured output), one call per intent: for every labelled text,
  whether its own meaning carries the intent, the kind of link, where in the
  text the meaning sits (word positions, never words), the link in a short
  Arabic sentence, the context a reader needs, the extra assumptions the link
  requires, and the reason of a rejection. Texts are labelled Q1, H1 ...: the
  model never handles a stored id and never writes a text. A text that fits
  only as a general reminder is rejected;
- eligibility of a hadith, decided by the server alone (decision 64): a hadith
  with no ruling is shown as it is; a hadith an editor ruled out may give way
  to an accepted hadith of the same relation tier, never a weaker one. A verse
  is always eligible: the store holds it exactly as quranpedia gives it;
- the pair: the verifier names the one verse and the one hadith that serve
  the same specific meaning, and a half it leaves open stays open; only when
  it names no pair does the server pair the strongest accepted verse with an
  accepted hadith of the same relation tier, and it never pairs two texts
  because each is best on its own. Inside a tier, a text the learner has not seen comes before
  one they have (v2 §11); when every text of the tier was seen, the best one
  is shown again as a review, never a weaker one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
from src.pipeline.insight.intents import SearchIntent
from src.pipeline.insight.search import VERIFY_TOP, Found
from src.pipeline.leak_guard import ScriptureLeakError
from src.pipeline.prompt import load_prompt
from src.pipeline.schemas import SceneAnalysis
from src.scripture import rulings
from src.scripture.text import search_copy

log = logging.getLogger(__name__)

SYSTEM_PROMPT = "evidence_verifier_system.v3"
MAX_OUTPUT_TOKENS = 4000
# Characters of folded text shown per candidate: a hadith's chain is already cut.
TEXT_CHARS = 600
# Strongest first (v2 §8); a general reminder is not a relation the verifier may accept.
RELATION_ORDER = {
    RelationType.DIRECT: 0,
    RelationType.ACTION_BASED: 1,
    RelationType.CLOSE_CONCEPTUAL: 2,
    RelationType.OPPOSITE: 3,
}
RelationName = Literal["direct", "action_based", "close_conceptual", "opposite", "none"]
RejectReason = Literal[
    "lexical_overlap",
    "overgeneralisation",
    "assumed_intent",
    "context_ignored",
    "direction_mismatch",
    "meaning_not_supported",
    "other",
]
# Rule 4: a grade or a word of authenticity in a field a reader sees is dropped by the server.
# Matched on the folded copy (no diacritics, no tatweel), so a spelling cannot slip past; the
# verb forms (صحح، ضعف) and the dataset's weak grades are in. «حسن» also catches ordinary words
# such as «أحسن»: a lost link is the safer loss.
GRADE_WORDS = re.compile(
    r"صحيح|صحح|حسن|ضعيف|ضعف|موضوع|ثابت|منكر|متواتر|مشهور|شاذ|معلول|مرسل|باطل|متروك|منقطع|مضطرب"
)
NOT_SEARCHED = "not_searched"
NOTHING_FOUND = "nothing_found"
NO_VERDICT = "no_verdict"


class TextJudgement(BaseModel):
    label: Annotated[str, Field(description="Q1, Q2 ... or H1, H2 ... as given.")]
    accepted: bool
    relation: RelationName
    basis_words: Annotated[list[int], Field(description="[first, last] word positions, or [].")]
    link: Annotated[
        str, Field(description="Arabic: how the text meets the intent; '' if rejected.")
    ]
    needed_context: Annotated[str | None, Field(description="Arabic, or null.")]
    assumptions: Annotated[
        list[str], Field(description="Arabic: extra assumptions the link needs.")
    ]
    reject_reason: RejectReason | None


class PairChoice(BaseModel):
    quran: Annotated[str | None, Field(description="An accepted Q label, or null.")]
    hadith: Annotated[str | None, Field(description="An accepted H label, or null.")]
    shared_meaning: Annotated[str, Field(description="Arabic: the meaning both serve.")]


class VerifierOutput(BaseModel):
    texts: list[TextJudgement]
    pair: PairChoice | None


@dataclass(frozen=True, slots=True)
class Shortlist:
    """What one intent's searches found, as the verifier will see it."""

    intent: SearchIntent
    quran: list[Found]
    hadith: list[Found]
    # Why a corpus list is empty, for the trace: not searched, or nothing found.
    quran_note: str | None = None
    hadith_note: str | None = None

    def labelled(self) -> dict[str, Found]:
        return {f"Q{i}": item for i, item in enumerate(self.quran, start=1)} | {
            f"H{i}": item for i, item in enumerate(self.hadith, start=1)
        }

    @property
    def empty(self) -> bool:
        return not self.quran and not self.hadith


@dataclass(frozen=True, slots=True)
class Verdict:
    """What the verifier said about one intent's shortlist."""

    judged: dict[str, TextJudgement]
    pair: PairChoice | None

    def accepted(self) -> dict[str, TextJudgement]:
        return {
            label: item
            for label, item in self.judged.items()
            if item.accepted and item.relation != "none"
        }


@dataclass(frozen=True, slots=True)
class Chosen:
    """The text behind one half of an insight, and why it was chosen."""

    found: Found
    relation: RelationType
    link: str
    assumptions: tuple[str, ...]
    needed_context: str | None
    basis_words: tuple[int, ...]
    review: bool
    unseen_preferred: bool


@dataclass
class GateResult:
    """What the gate decided for one intent."""

    intent: SearchIntent
    quran: Chosen | None = None
    hadith: Chosen | None = None
    quran_ref: QuranRef | None = None
    hadith_ref: HadithRef | None = None
    shared_meaning: str | None = None
    # Why each judged text was not kept, by label, for the trace and the refinement.
    rejections: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.quran is not None or self.hadith is not None

    @property
    def pair_complete(self) -> bool:
        return self.quran is not None and self.hadith is not None

    @property
    def relation(self) -> RelationType:
        """The weakest of the intent's relation and the chosen texts' own relations."""
        relations = [self.intent.relation] + [
            c.relation for c in (self.quran, self.hadith) if c is not None
        ]
        return max(relations, key=RELATION_ORDER.__getitem__)

    def reasons(self) -> tuple[str, ...]:
        """Return the rejection reasons, most frequent first, for a refinement round."""
        counts: dict[str, int] = {}
        for reason in self.rejections.values():
            counts[reason] = counts.get(reason, 0) + 1
        return tuple(sorted(counts, key=lambda reason: (-counts[reason], reason)))

    def as_trace(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent.intent_id,
            "quran": self.quran.found.key if self.quran else None,
            "hadith": self.hadith.found.key if self.hadith else None,
            "pair_complete": self.pair_complete,
            "relation": self.relation.value,
            "rejections": dict(self.rejections),
        }


def verifier_message(scene: SceneAnalysis, shortlist: Shortlist) -> str:
    """Assemble what the verifier reads: the scene, the one intent, its texts. No learner."""
    intent = shortlist.intent
    payload: dict[str, Any] = {
        "scene": {
            "description": scene.description,
            "entities": [entity.label_arabic for entity in scene.entities],
            "actions": [action.label for action in scene.actions],
        },
        "intent": {
            "observable_meaning": intent.observable_meaning,
            "relation_description": intent.relation_description,
            "candidate_concept": intent.candidate_concept,
            "concept_basis": intent.concept_basis,
            "relation_claimed": intent.relation.value,
            "uncertainties": list(intent.uncertainties),
            "unsupported_assumptions": list(intent.unsupported_assumptions),
        },
        "texts": [
            {"label": label, "text": found.document.text[:TEXT_CHARS]}
            for label, found in shortlist.labelled().items()
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def verdict_texts(output: VerifierOutput) -> dict[str, str]:
    """Every free text of a verdict, for the leak guard."""
    texts: dict[str, str] = {}
    for item in output.texts:
        if item.link.strip():
            texts[f"{item.label}.link"] = item.link
        if item.needed_context and item.needed_context.strip():
            texts[f"{item.label}.needed_context"] = item.needed_context
        texts |= {
            f"{item.label}.assumptions.{i}": text
            for i, text in enumerate(item.assumptions)
            if text.strip()
        }
    if output.pair is not None and output.pair.shared_meaning.strip():
        texts["pair.shared_meaning"] = output.pair.shared_meaning
    return texts


class EvidenceRelevanceVerifier:
    """Tests every shortlisted text against its intent, one call per intent, all at once."""

    def __init__(self, client: ModelClient, *, attempts: int = 2) -> None:
        self._client = client
        self._attempts = attempts

    async def verify(
        self, scene: SceneAnalysis, shortlists: Sequence[Shortlist], guard: EngineGuard
    ) -> dict[int, Verdict | None]:
        """
        Return, per shortlist index, the verdict on each label and the pair.

        An empty shortlist gets no call and no entry; an intent whose answers kept leaking
        gets None, so the caller can tell a model fault from «no text fits». The calls run
        together: a verdict never depends on another intent. The first error of any call is
        raised.
        """
        indexed = [(i, s) for i, s in enumerate(shortlists) if not s.empty]
        judged = await asyncio.gather(
            *(self._verify_one(scene, shortlist, guard) for _, shortlist in indexed),
            return_exceptions=True,
        )
        for outcome in judged:
            if isinstance(outcome, BaseException):
                raise outcome
        return {
            index: verdict if isinstance(verdict, Verdict) else None
            for (index, _), verdict in zip(indexed, judged, strict=True)
        }

    async def _verify_one(
        self, scene: SceneAnalysis, shortlist: Shortlist, guard: EngineGuard
    ) -> Verdict | None:
        """Judge one intent's texts; an answer that leaks is asked again, then dropped."""
        system = load_prompt(SYSTEM_PROMPT)
        user = verifier_message(scene, shortlist)
        known = shortlist.labelled()
        for attempt in range(1, self._attempts + 1):
            result = await self._client.chat_json(
                VerifierOutput,
                stage=AiStage.VERIFY,
                system=system.text,
                user=user,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            try:
                await guard.ensure_clean(verdict_texts(result.value))
            except ScriptureLeakError as error:
                log.warning("verifier answer refused (attempt %d): %s", attempt, error)
                continue
            judged = {t.label: t for t in result.value.texts if t.label in known}
            return Verdict(judged, result.value.pair)
        # Still leaking: this intent gets no verdict, so none of its texts passes the gate.
        return None


def _tier(
    labels: Sequence[str], accepted: dict[str, TextJudgement], relation: RelationType
) -> list[str]:
    return [label for label in labels if RelationType(accepted[label].relation) is relation]


def _best_label(
    labels: Sequence[str], accepted: dict[str, TextJudgement], prefer: RelationType | None
) -> str | None:
    """Return the first accepted label of the preferred tier, else of the strongest; never across tiers."""
    if not labels:
        return None
    if prefer is not None:
        same = _tier(labels, accepted, prefer)
        return same[0] if same else None
    return min(labels, key=lambda label: RELATION_ORDER[RelationType(accepted[label].relation)])


def _clean_field(text: str | None) -> str:
    """Return a reader-facing field written by the verifier, or nothing when it grades a hadith."""
    cleaned = (text or "").strip()
    return "" if GRADE_WORDS.search(search_copy(cleaned)) else cleaned


def _chosen(
    label: str,
    labelled: dict[str, Found],
    accepted: dict[str, TextJudgement],
    tier: Sequence[str],
    seen: frozenset[int],
) -> Chosen:
    """Keep `label`, unless it was seen and another text of its tier was not (v2 §11)."""
    unseen = [item for item in tier if labelled[item].key not in seen]
    final = label if labelled[label].key not in seen or not unseen else unseen[0]
    judgement = accepted[final]
    return Chosen(
        found=labelled[final],
        relation=RelationType(judgement.relation),
        link=_clean_field(judgement.link),
        assumptions=tuple(a for a in map(_clean_field, judgement.assumptions) if a),
        needed_context=_clean_field(judgement.needed_context) or None,
        basis_words=tuple(judgement.basis_words[:2]),
        review=final == label and labelled[label].key in seen,
        unseen_preferred=final != label,
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
    verdict: Verdict | None,
    *,
    seen_verses: frozenset[int],
    seen_hadiths: frozenset[int],
) -> GateResult:
    """Apply relevance, then eligibility, then the pair and the learner's history to one intent."""
    labelled = shortlist.labelled()
    result = GateResult(shortlist.intent)
    for name, note in (("Q", shortlist.quran_note), ("H", shortlist.hadith_note)):
        if note:
            result.rejections[name] = note
    if verdict is None:
        result.rejections |= dict.fromkeys(labelled, NO_VERDICT)
        return result
    accepted = verdict.accepted()
    for label, judgement in verdict.judged.items():
        if label not in accepted:
            result.rejections[label] = judgement.reject_reason or "meaning_not_supported"
    verse_label, hadith_label = _pair_labels(labelled, accepted, verdict.pair)
    if verdict.pair is not None and verdict.pair.shared_meaning.strip():
        result.shared_meaning = verdict.pair.shared_meaning.strip()
    if verse_label is not None:
        verses = [label for label in labelled if label.startswith("Q") and label in accepted]
        tier = _tier(verses, accepted, RelationType(accepted[verse_label].relation))
        result.quran = _chosen(verse_label, labelled, accepted, tier, seen_verses)
        result.quran_ref = await quran_ref(session, result.quran.found.key)
    if hadith_label is not None:
        await _choose_hadith(session, result, labelled, accepted, hadith_label, seen_hadiths)
    if result.shared_meaning is None and result.passed:
        result.shared_meaning = shortlist.intent.candidate_concept
    return result


def _pair_labels(
    labelled: dict[str, Found], accepted: dict[str, TextJudgement], pair: PairChoice | None
) -> tuple[str | None, str | None]:
    """
    Return the verse and hadith labels of the pair.

    The verifier's choice stands, a half it left open included: null means no accepted text of
    that corpus serves the shared meaning. Only when it named no pair at all does the server
    pair the strongest accepted verse with an accepted hadith of the same relation tier, so the
    pair serves one meaning at one distance; a label it named that was not accepted counts as
    open.
    """
    verses = [label for label in labelled if label.startswith("Q") and label in accepted]
    hadiths = [label for label in labelled if label.startswith("H") and label in accepted]
    if pair is not None:
        verse_label = pair.quran if pair.quran in verses else None
        hadith_label = pair.hadith if pair.hadith in hadiths else None
        return verse_label, hadith_label
    verse_label = _best_label(verses, accepted, None)
    prefer = RelationType(accepted[verse_label].relation) if verse_label else None
    return verse_label, _best_label(hadiths, accepted, prefer)


async def _choose_hadith(
    session: AsyncSession,
    result: GateResult,
    labelled: dict[str, Found],
    accepted: dict[str, TextJudgement],
    label: str,
    seen: frozenset[int],
) -> None:
    """Keep the wanted hadith when eligible; replace a ruled-out one within its tier, or not at all."""
    hadiths = [name for name in labelled if name.startswith("H") and name in accepted]
    tier = _tier(hadiths, accepted, RelationType(accepted[label].relation))
    eligible = [name for name in tier if await rulings.is_eligible(session, labelled[name].key)]
    if label in eligible:
        result.hadith = _chosen(label, labelled, accepted, eligible, seen)
    else:
        # Ruled out by an editor: an accepted hadith of the same tier may stand in, never a
        # weaker one.
        result.rejections[label] = "ruled_ineligible"
        if eligible:
            result.hadith = _chosen(eligible[0], labelled, accepted, eligible, seen)
    if result.hadith is not None:
        # Shown without a ruling: counted so the editors see which hadiths are shown most.
        await rulings.enqueue_demand(session, result.hadith.found.key)
        result.hadith_ref = await hadith_ref(session, result.hadith.found.key)


def shortlist_of(
    intent: SearchIntent,
    quran: Sequence[Found],
    hadith: Sequence[Found],
    *,
    top: int = VERIFY_TOP,
    quran_note: str | None = None,
    hadith_note: str | None = None,
) -> Shortlist:
    return Shortlist(
        intent,
        list(quran[:top]),
        list(hadith[:top]),
        quran_note=quran_note,
        hadith_note=hadith_note,
    )
