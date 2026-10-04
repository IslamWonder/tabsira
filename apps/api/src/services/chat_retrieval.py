"""
A chat request for another text runs the retrieval and the verification again (v2 §14).

«طلب نص إضافي يعيد الاسترجاع والتحقق؛ لا جواب من الذاكرة»: when the learner asks
for a verse or a hadith the insight does not show, no model answers from memory.
The planner is not called: one candidate is built from the insight's concept and
the learner's own words, and goes through the engine's stages as a scan does:

- the hybrid search of `src.pipeline.insight.search`, with the embedding and
  the reranker the settings name, the insight's own texts left out;
- the verifier, judging the shortlist against the scan's stored scene;
- the gate, with its rules unchanged: a hadith without an eligible ruling is
  queued for an editor (decision 18) and never shown, a remote companion is
  dropped.

The cost is one embedding call and one verifier call. Nothing here writes a
text: the result is references, read from the store by the view.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.config import Settings
from src.models import EmbeddedCorpus, Hadith, Insight, QuranVerse, Scan
from src.pipeline.engine import HadithRef, RelationType
from src.pipeline.insight.engine import ResourceCache, build_reranker
from src.pipeline.insight.evidence import gate, shortlist_of, verify
from src.pipeline.insight.guard import scripture_guard
from src.pipeline.insight.planner import PlannedCandidate
from src.pipeline.insight.search import Embedding, EvidenceSearch, Found, embed_queries
from src.pipeline.schemas import SceneAnalysis
from src.routers.scripture import HadithOut, QuranVerseOut, read_hadith, read_verse

log = logging.getLogger("tabsira.chat.retrieval")

TextKind = Literal["verse", "hadith", "either"]
# The learner's words kept in the query: the planner's queries are short, and a
# message is a sentence or two; the rest only dilutes the lexical and vector lists.
QUERY_WORDS = 24


@dataclass(frozen=True, slots=True)
class NewText:
    """What the focused run found and what the gate let through."""

    verse: QuranVerseOut | None = None
    hadith: HadithOut | None = None
    # The hadith the gate wanted that waits for an editor's ruling (decision 18).
    awaiting: list[HadithRef] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verse is not None or self.hadith is not None

    @property
    def ids(self) -> set[str]:
        """The evidence ids of the texts that passed, as the chat message keeps them."""
        ids = set()
        if self.verse is not None:
            ids.add(f"quran:{self.verse.surah}:{self.verse.ayah}")
        if self.hadith is not None:
            ids.add(f"hadith:{self.hadith.collection.slug}:{self.hadith.number}")
        return ids


def query_for(concept: str, question: str) -> str:
    """Return the one query of the run: the insight's concept, then the learner's words."""
    words = f"{concept} {question}".split()
    return " ".join(words[:QUERY_WORDS])


def candidate_for(insight: Insight, question: str, kind: TextKind) -> PlannedCandidate:
    """Build the one candidate of the run from what the insight already settled."""
    why = insight.why
    query = query_for(str(why.get("concept", "")), question)
    queries = (query,)
    return PlannedCandidate(
        title=insight.title,
        glimpse=insight.glimpse,
        concept=str(why.get("concept", "")),
        value=insight.glimpse,
        relation=RelationType(insight.relation),
        entity_ids=tuple(insight.entity_ids),
        action_ids=tuple(insight.action_ids),
        quran_queries=queries if kind in {"verse", "either"} else (),
        hadith_queries=queries if kind in {"hadith", "either"} else (),
        ontology_ids=(),
        unit=None,
        content_level="a",
        visible_clues=tuple(str(clue) for clue in why.get("visible_clues", [])),
        limits=tuple(str(limit) for limit in why.get("limits", [])),
    )


async def own_ids(db: AsyncSession, insight: Insight) -> tuple[frozenset[int], frozenset[int]]:
    """Return the ids of the insight's own verse and hadith: the learner has those already."""
    verses: frozenset[int] = frozenset()
    hadiths: frozenset[int] = frozenset()
    if insight.quran_surah is not None and insight.quran_ayah is not None:
        verses = frozenset(
            await db.scalars(
                select(QuranVerse.id).where(
                    QuranVerse.surah == insight.quran_surah, QuranVerse.ayah == insight.quran_ayah
                )
            )
        )
    if insight.hadith_collection is not None and insight.hadith_number is not None:
        hadiths = frozenset(
            await db.scalars(
                select(Hadith.id).where(
                    Hadith.collection == insight.hadith_collection,
                    Hadith.number == insight.hadith_number,
                )
            )
        )
    return verses, hadiths


async def stored_scene(db: AsyncSession, insight: Insight) -> SceneAnalysis | None:
    """Return the verified scene of the insight's scan; none for an insight without one."""
    scan = await db.get(Scan, insight.scan_id) if insight.scan_id is not None else None
    if scan is None or scan.scene is None:
        return None
    return SceneAnalysis.model_validate(scan.scene)


def _without(found: list[Found], excluded: frozenset[int]) -> list[Found]:
    return [item for item in found if item.key not in excluded]


async def find_new_text(
    db: AsyncSession,
    settings: Settings,
    insight: Insight,
    client: ModelClient,
    *,
    question: str,
    kind: TextKind,
    http: httpx.AsyncClient | None,
    resources: ResourceCache,
) -> NewText:
    """
    Search, verify and gate one new text for the learner's request.

    Returns what passed (nothing when the insight has no scene to judge against,
    when the searches found nothing, or when the gate let nothing through). A
    model call that fails raises `AiCallError`, as the engine's stages do. The
    cross-encoder reranker needs `http`; a caller without one (the evaluation)
    gets a client for the call.
    """
    scene = await stored_scene(db, insight)
    if scene is None:
        return NewText()
    if http is not None:
        return await _find(db, settings, insight, client, scene, question, kind, http, resources)
    async with httpx.AsyncClient() as owned:
        return await _find(db, settings, insight, client, scene, question, kind, owned, resources)


async def _find(
    db: AsyncSession,
    settings: Settings,
    insight: Insight,
    client: ModelClient,
    scene: SceneAnalysis,
    question: str,
    kind: TextKind,
    http: httpx.AsyncClient,
    resources: ResourceCache,
) -> NewText:
    loaded = await resources.get(db)
    block = settings.ai
    embedding = (
        Embedding(client, block.embedding_model, block.embedding_dimensions)
        if block.embedding_model
        else None
    )
    search = EvidenceSearch(
        embedding=embedding,
        reranker=build_reranker(settings, http, client),
        concepts=loaded.concepts,
    )
    candidate = candidate_for(insight, question, kind)
    queries = [*candidate.quran_queries, *candidate.hadith_queries]
    vectors, embed_error = await embed_queries(embedding, queries)
    if embed_error:
        log.warning("query embedding skipped: %s; searching without vectors", embed_error)
    own_verses, own_hadiths = await own_ids(db, insight)
    searched: list[tuple[tuple[str, ...], list[Found]]] = []
    for corpus, corpus_queries, own in (
        (EmbeddedCorpus.QURAN, candidate.quran_queries, own_verses),
        (EmbeddedCorpus.HADITH, candidate.hadith_queries, own_hadiths),
    ):
        found = await search.search(db, corpus, corpus_queries, vectors) if corpus_queries else []
        searched.append((corpus_queries, _without(found, own)))
    results = await asyncio.gather(*(search.rerank(q, found) for q, found in searched))
    for result in results:
        if result.rerank_error:
            log.warning("reranker skipped: %s; fused order kept", result.rerank_error)
    shortlist = shortlist_of(candidate, results[0].found, results[1].found)
    if not shortlist.quran and not shortlist.hadith:
        return NewText()
    texts = [found.document.text for found in shortlist.hadith]
    verdicts = await verify(client, scene, [shortlist], scripture_guard(loaded.quran, texts, db))
    gated = await gate(
        db, shortlist, verdicts.get(0, {}), seen_verses=frozenset(), seen_hadiths=frozenset()
    )
    verse = (
        await read_verse(db, gated.quran_ref.surah, gated.quran_ref.ayah)
        if gated.quran_ref is not None
        else None
    )
    hadith = (
        await read_hadith(db, gated.hadith_ref.collection, gated.hadith_ref.number)
        if gated.hadith_ref is not None
        else None
    )
    return NewText(verse=verse, hadith=hadith, awaiting=list(gated.awaiting))
