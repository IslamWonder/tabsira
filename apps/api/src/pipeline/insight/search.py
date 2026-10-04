"""
Find the evidence a candidate insight's queries point to: hybrid search, then the reranker.

For each corpus (the Quran and the hadiths are searched apart) every query of
the candidate runs three searches: vector (the provider's embedding model),
full text over the search copies, and the model-written concepts; the unit's
anchors from the learning path join as a fourth list. Reciprocal Rank Fusion
makes one list of them (docs/BENCHMARK.md measured the choices), and the
cross-encoder of services/vision reorders its head. Each step that fails is
skipped and recorded: no vectors when the embedding call fails, the fused
order when the reranker does not answer. Nothing here is ever displayed; a
result is ids, scores and the query that found them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.ai.errors import AiCallError
from src.models import EmbeddedCorpus
from src.retrieval.concepts import ConceptIndex
from src.retrieval.documents import RetrievalDocument, hadith_documents, quran_documents
from src.retrieval.fusion import FusedHit, fuse
from src.retrieval.lexical import Hit, search_lexical
from src.retrieval.query import query_terms
from src.retrieval.reranker import RerankerClient
from src.retrieval.vector import nearest

# Candidates each search returns, and the head of the fused list the cross-encoder reads:
# eight, not thirty, because on a CPU it reads about 1.5 passages a second (docs/BENCHMARK.md)
# and the verifier sees only the first four of each corpus.
SEARCH_TOP = 30
RERANK_TOP = 8
QUERY_SEPARATOR = " ، "


@dataclass(frozen=True, slots=True)
class Found:
    """A stored text a search found, with how it was found."""

    corpus: EmbeddedCorpus
    key: int
    retrieval_score: float
    rerank_score: float | None
    matched_on: str
    document: RetrievalDocument


@dataclass(frozen=True, slots=True)
class SearchResult:
    found: list[Found]
    rerank_error: str | None = None
    rerank_ms: int = 0


@dataclass(frozen=True, slots=True)
class Embedding:
    """The model and size of the query vectors, matching the stored ones."""

    client: ModelClient
    model: str
    dimensions: int | None


async def embed_queries(
    embedding: Embedding | None, queries: Sequence[str]
) -> tuple[dict[str, list[float]], str | None]:
    """Embed every distinct query in one call; on failure return none and the reason."""
    distinct = list(dict.fromkeys(queries))
    if embedding is None or not distinct:
        return {}, None
    try:
        result = await embedding.client.embed(
            distinct, model=embedding.model, dimensions=embedding.dimensions
        )
    except AiCallError as error:
        return {}, error.code.value
    return dict(zip(distinct, result.vectors, strict=True)), None


def _matched_on(hit: FusedHit, queries: Sequence[str]) -> str:
    """Return the query of the list that ranked this text best."""
    best = min(hit.ranks, key=lambda item: item[1])[0]
    index = best.rsplit(":", 1)[1]
    return queries[int(index)] if index.isdigit() else QUERY_SEPARATOR.join(queries)


async def _documents(
    session: AsyncSession, corpus: EmbeddedCorpus, keys: Sequence[int], index: ConceptIndex
) -> dict[int, RetrievalDocument]:
    found = (
        await quran_documents(session, list(keys))
        if corpus is EmbeddedCorpus.QURAN
        else await hadith_documents(session, hadith_ids=list(keys), concepts=index.concepts)
    )
    return {document.key: document for document in found}


class EvidenceSearch:
    """Hybrid search and rerank over one corpus at a time."""

    def __init__(
        self,
        *,
        embedding: Embedding | None,
        reranker: RerankerClient | None,
        concepts: Mapping[EmbeddedCorpus, ConceptIndex],
        rerank_top: int = RERANK_TOP,
    ) -> None:
        self._embedding = embedding
        self._reranker = reranker
        self._concepts = concepts
        self._rerank_top = rerank_top

    async def search(
        self,
        session: AsyncSession,
        corpus: EmbeddedCorpus,
        queries: Sequence[str],
        vectors: Mapping[str, list[float]],
        *,
        anchors: Sequence[int] = (),
    ) -> SearchResult:
        """Return the fused, reranked candidates of `queries` in `corpus`, best first."""
        lists: dict[str, Sequence[Hit]] = {}
        for index, query in enumerate(queries):
            lists[f"fts:{index}"] = await search_lexical(
                session, corpus, query_terms(query), limit=SEARCH_TOP
            )
            lists[f"concepts:{index}"] = self._concepts[corpus].search(query, limit=SEARCH_TOP)
            if query in vectors and self._embedding is not None:
                lists[f"vector:{index}"] = await nearest(
                    session,
                    corpus,
                    vectors[query],
                    model=self._embedding.model,
                    dimensions=len(vectors[query]),
                    limit=SEARCH_TOP,
                )
        if anchors:
            lists["anchors:path"] = [Hit(key, 1.0) for key in anchors]
        fused = fuse(lists)[:SEARCH_TOP]
        if not fused:
            return SearchResult([])
        documents = await _documents(
            session, corpus, [hit.key for hit in fused], self._concepts[corpus]
        )
        found = [
            Found(corpus, hit.key, hit.score, None, _matched_on(hit, queries), documents[hit.key])
            for hit in fused
            if hit.key in documents
        ]
        return await self._reranked(QUERY_SEPARATOR.join(queries), found)

    async def _reranked(self, query: str, found: list[Found]) -> SearchResult:
        if self._reranker is None:
            return SearchResult(found)
        head, tail = found[: self._rerank_top], found[self._rerank_top :]
        outcome = await self._reranker.rerank(query, [item.document.body for item in head])
        if outcome.scores is None:
            return SearchResult(found, outcome.error, outcome.latency_ms)
        scored = [
            Found(
                item.corpus, item.key, item.retrieval_score, score, item.matched_on, item.document
            )
            for item, score in zip(head, outcome.scores, strict=True)
        ]
        scored.sort(key=lambda item: -(item.rerank_score or 0.0))
        return SearchResult(scored + tail, None, outcome.latency_ms)
