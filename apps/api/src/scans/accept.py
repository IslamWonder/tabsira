"""
What the workflow accepts from the engine, checked again on the server before anything is saved.

The engine is trusted for nothing it can get wrong silently:
- a verse or a hadith it cites must be in the store; a hadith whose editor
  ruling is not صحيح or حسن is never kept as evidence, and one without a ruling
  is kept (shown once ruled) and counted in the verification queue;
- an insight left with nothing it can show now (no verse, and no hadith with
  an eligible ruling) is dropped: no source, no scripture (v2 rule 1);
- every text it wrote goes through the leak guard, with the cited texts
  (refused ones included) as a corpus, and is compared with every verse and
  hadith of the store, so a quotation hidden in an explanation refuses the insight;
- an explanation part or a small step may rest only on the insight's own
  verse or hadith (`quran:S:A`, `hadith:C:N`) or on a learning unit that
  exists (`masar:T01_06`); one that names anything else is dropped;
- entity ids must be the scene's, the learning unit must be in its path
  version, and there are three insights at most.
Each refusal is recorded by a stable reason, never with the refused text.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Hadith, LearningUnit, QuranVerse
from src.pipeline.engine import EvidenceRef, HadithRef, ProposedInsight, QuranRef
from src.pipeline.leak_guard import LeakGuard, PatternLeakDetector, ShingleOverlapDetector
from src.pipeline.schemas import SceneAnalysis
from src.scripture.overlap import repeats_store
from src.scripture.rulings import classification_is_eligible, enqueue_demand, latest_ruling

MAX_INSIGHTS = 3
UNIT_PREFIX = "masar:"


@dataclass(frozen=True)
class Accepted:
    insights: list[ProposedInsight]
    # Why insights or parts of them were refused: `leak`, `no_evidence`, `quran_missing`, ...
    refusals: list[str] = field(default_factory=list)


def insight_texts(insight: ProposedInsight) -> dict[str, str]:
    """Every free text the engine wrote for an insight, keyed by where it is."""
    texts = {"title": insight.title, "glimpse": insight.glimpse}
    texts |= {f"explanation.{i}": part.text for i, part in enumerate(insight.explanation)}
    texts |= {f"why.clue.{i}": clue for i, clue in enumerate(insight.why.visible_clues)}
    texts |= {f"why.limit.{i}": limit for i, limit in enumerate(insight.why.limits)}
    texts["why.concept"] = insight.why.concept
    if insight.why.personalised_because:
        texts["why.personalised_because"] = insight.why.personalised_because
    if insight.small_step is not None:
        texts["small_step"] = insight.small_step.text
    for name, evidence in (("quran", insight.quran), ("hadith", insight.hadith)):
        if evidence is not None:
            texts[f"{name}.matched_on"] = evidence.matched_on
    return texts


async def _verse_text(db: AsyncSession, surah: int, ayah: int) -> str | None:
    text: str | None = await db.scalar(
        select(QuranVerse.text).where(QuranVerse.surah == surah, QuranVerse.ayah == ayah)
    )
    return text


async def _hadith(db: AsyncSession, ref: HadithRef) -> Hadith | None:
    found: Hadith | None = await db.scalar(
        select(Hadith).where(Hadith.collection == ref.collection, Hadith.number == ref.number)
    )
    return found


async def accept(
    db: AsyncSession,
    scene: SceneAnalysis,
    proposed: Iterable[ProposedInsight],
    *,
    awaiting_ruling: Iterable[HadithRef] = (),
) -> Accepted:
    """Return the insights that pass every check, rewritten to what was verified."""
    refusals: list[str] = []
    kept: list[ProposedInsight] = []
    entity_ids = {entity.id for entity in scene.entities}
    boxes = {entity.id: entity.bbox for entity in scene.entities}
    for insight in list(proposed)[:MAX_INSIGHTS]:
        checked = await _check(db, insight, refusals)
        if checked is None:
            continue
        checked = await _placed(db, checked, refusals)
        ids = [entity_id for entity_id in checked.entity_ids if entity_id in entity_ids]
        anchor = checked.anchor or next((boxes[i] for i in ids if boxes[i] is not None), None)
        unit = checked.learning_unit_id
        if unit is not None and not await _unit_exists(db, unit, checked.learning_path_version):
            refusals.append("unknown_unit")
            unit = None
        kept.append(
            checked.model_copy(
                update={
                    "entity_ids": ids,
                    "anchor": anchor,
                    "learning_unit_id": unit,
                    "learning_path_version": checked.learning_path_version if unit else None,
                }
            )
        )
    for ref in awaiting_ruling:
        stored = await _hadith(db, ref)
        if stored is not None:
            await enqueue_demand(db, stored.id)
    return Accepted(insights=kept, refusals=refusals)


async def _checked_quran(
    db: AsyncSession, evidence: EvidenceRef | None, corpus: list[str], refusals: list[str]
) -> EvidenceRef | None:
    if evidence is None:
        return None
    if not isinstance(evidence.ref, QuranRef):
        refusals.append("quran_kind")
        return None
    text = await _verse_text(db, evidence.ref.surah, evidence.ref.ayah)
    if text is None:
        refusals.append("quran_missing")
        return None
    corpus.append(text)
    return evidence


async def _checked_hadith(
    db: AsyncSession, evidence: EvidenceRef | None, corpus: list[str], refusals: list[str]
) -> tuple[EvidenceRef | None, bool]:
    """Return the hadith kept, and whether its ruling lets it show now."""
    if evidence is None:
        return None, False
    if not isinstance(evidence.ref, HadithRef):
        refusals.append("hadith_kind")
        return None, False
    stored = await _hadith(db, evidence.ref)
    if stored is None:
        refusals.append("hadith_missing")
        return None, False
    # Guarded against even when it is refused: the engine's words may still quote it.
    corpus.append(stored.text)
    ruling = await latest_ruling(db, stored.id)
    if ruling is None:
        await enqueue_demand(db, stored.id)
        return evidence, False
    if not classification_is_eligible(ruling.classification):
        refusals.append("hadith_ineligible")
        return None, False
    return evidence, True


async def _check(
    db: AsyncSession, insight: ProposedInsight, refusals: list[str]
) -> ProposedInsight | None:
    corpus: list[str] = []
    quran = await _checked_quran(db, insight.quran, corpus, refusals)
    hadith, hadith_shows = await _checked_hadith(db, insight.hadith, corpus, refusals)
    if quran is None and hadith is None:
        refusals.append("no_evidence")
        return None
    if quran is None and not hadith_shows:
        # A hadith waiting for its ruling is not shown, and there is no verse to show.
        refusals.append("nothing_to_show")
        return None
    guard = LeakGuard([PatternLeakDetector(), ShingleOverlapDetector(corpus)])
    texts = list(insight_texts(insight).values())
    if any(guard.check(text).leaked for text in texts) or await repeats_store(db, texts):
        refusals.append("leak")
        return None
    return insight.model_copy(update={"quran": quran, "hadith": hadith})


def _cited_ids(insight: ProposedInsight) -> set[str]:
    cited = set()
    for evidence in (insight.quran, insight.hadith):
        ref = evidence.ref if evidence is not None else None
        if isinstance(ref, QuranRef):
            cited.add(f"quran:{ref.surah}:{ref.ayah}")
        elif isinstance(ref, HadithRef):
            cited.add(f"hadith:{ref.collection}:{ref.number}")
    return cited


async def _placed(
    db: AsyncSession, insight: ProposedInsight, refusals: list[str]
) -> ProposedInsight:
    """Drop the parts and the step that rest on anything but the insight's texts or a unit."""
    named = {
        ref.removeprefix(UNIT_PREFIX)
        for refs in [
            *(part.sources for part in insight.explanation),
            insight.small_step.grounded_in if insight.small_step else [],
        ]
        for ref in refs
        if ref.startswith(UNIT_PREFIX)
    }
    units = set(
        (await db.scalars(select(LearningUnit.id).where(LearningUnit.id.in_(named)))).all()
        if named
        else []
    )
    known = _cited_ids(insight) | {f"{UNIT_PREFIX}{unit}" for unit in units}

    def placed(refs: list[str]) -> bool:
        if all(ref in known for ref in refs):
            return True
        refusals.append("unknown_reference")
        return False

    step = insight.small_step
    return insight.model_copy(
        update={
            "explanation": [part for part in insight.explanation if placed(part.sources)],
            "small_step": step if step is None or placed(step.grounded_in) else None,
        }
    )


async def _unit_exists(db: AsyncSession, unit_id: str, path_version: str | None) -> bool:
    if path_version is None:
        return False
    found = await db.scalar(
        select(LearningUnit.id).where(
            LearningUnit.id == unit_id, LearningUnit.path_version == path_version
        )
    )
    return found is not None
