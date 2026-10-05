"""
A chat request for another text runs the retrieval and the verification again (v2 §14).

«طلب نص إضافي يعيد الاسترجاع والتحقق؛ لا جواب من الذاكرة»: when the learner asks
for a verse or a hadith the insight does not show, no model answers from memory.
The planner is not called: one search intent is built from the insight's
concept and the learner's own words, and goes through the engine's stages as a
scan does:

- the hybrid search of `src.pipeline.insight.search`, with the embedding and
  the reranker the settings name, the insight's own texts left out;
- the relevance verifier, testing the shortlist against the scan's stored scene;
- the gate, with its rules unchanged: a hadith an editor ruled out is never
  shown (decision 64).

The cost is one embedding call and one verifier call. A query embedding that
fails is raised as the model fault it is, never answered as «nothing found».
Nothing here writes a text: the result is references, read from the store by
the view.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.ai.errors import AiCallError, AiErrorCode
from src.config import Settings
from src.models import EmbeddedCorpus, Hadith, Insight, QuranVerse, Scan
from src.pipeline.engine import RelationType
from src.pipeline.insight.engine import ResourceCache, build_reranker
from src.pipeline.insight.evidence import EvidenceRelevanceVerifier, gate, shortlist_of
from src.pipeline.insight.guard import scripture_guard
from src.pipeline.insight.intents import IntentQueries, SearchIntent
from src.pipeline.insight.search import (
    Embedding,
    EvidenceSearch,
    Found,
    SearchResult,
    embed_queries,
    rerank_query,
)
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


CHAT_INTENT_ID = "chat"
NONE = IntentQueries((), ())


def intent_for(insight: Insight, question: str, kind: TextKind) -> SearchIntent:
    """Build the one intent of the run from what the insight already settled."""
    why = insight.why
    concept = str(why.get("concept", ""))
    query = query_for(concept, question)
    # The learner's sentence is both the keyword query and the sentence the vectors read.
    queries = IntentQueries(lexical=(query,), semantic=(query,))
    relation = RelationType(insight.relation)
    if relation is RelationType.THEMATIC_REMINDER:
        relation = RelationType.CLOSE_CONCEPTUAL
    return SearchIntent(
        intent_id=CHAT_INTENT_ID,
        entity_ids=tuple(insight.entity_ids),
        action_ids=tuple(insight.action_ids),
        observable_meaning=insight.glimpse,
        relation_description=None,
        candidate_concept=concept,
        concept_basis=insight.glimpse,
        relation=relation,
        content_level="a",
        uncertainties=tuple(str(limit) for limit in why.get("limits", [])),
        unsupported_assumptions=(),
        queries={
            EmbeddedCorpus.QURAN: queries if kind in {"verse", "either"} else NONE,
            EmbeddedCorpus.HADITH: queries if kind in {"hadith", "either"} else NONE,
        },
        ontology_ids=(),
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
    intent = intent_for(insight, question, kind)
    sentences = [q for corpus in EmbeddedCorpus for q in intent.queries_of(corpus).semantic]
    vectors, embed_error = await embed_queries(embedding, sentences)
    if embed_error:
        raise AiCallError(AiErrorCode(embed_error), "the query embedding failed")
    own_verses, own_hadiths = await own_ids(db, insight)
    searched: list[tuple[str, list[Found]]] = []
    for corpus, own in ((EmbeddedCorpus.QURAN, own_verses), (EmbeddedCorpus.HADITH, own_hadiths)):
        queries = intent.queries_of(corpus)
        found = [] if queries.empty else await search.search(db, corpus, queries, vectors)
        searched.append((rerank_query(queries, intent.observable_meaning), _without(found, own)))
    results: list[SearchResult] = await asyncio.gather(
        *(search.rerank(q, found) for q, found in searched)
    )
    for result in results:
        if result.rerank_error:
            log.warning("reranker skipped: %s; fused order kept", result.rerank_error)
    shortlist = shortlist_of(intent, results[0].found, results[1].found)
    if shortlist.empty:
        return NewText()
    texts = [found.document.text for found in shortlist.hadith]
    verdicts = await EvidenceRelevanceVerifier(client).verify(
        scene, [shortlist], scripture_guard(loaded.quran, texts, db)
    )
    verdict = verdicts.get(0)
    if verdict is None:
        # The verifier kept writing scripture-like text: a model fault, never «nothing found».
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "the verifier kept leaking")
    gated = await gate(db, shortlist, verdict, seen_verses=frozenset(), seen_hadiths=frozenset())
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
    return NewText(verse=verse, hadith=hadith)
