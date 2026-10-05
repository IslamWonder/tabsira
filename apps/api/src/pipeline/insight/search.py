"""
Find the evidence a search intent points to: hybrid search over one corpus, then the reranker.

For each corpus (the Quran and the hadiths are searched apart and stay apart
until the pair is chosen) an intent runs two kinds of lists, over the whole
corpus or over a pool of it (the narrations of the enriched Sunnah file, the
brief of 2026-10-05 §7: the file is the candidate source, the store identifies
and shows the text; one narration per record is kept, the best ranked):

- lexical: each keyword query over the full-text search copies (BM25-weighted
  prefix matching) and over the model-written concepts of the texts;
- semantic: each natural-sentence query as a vector against the stored
  document vectors of the same model and size.

Reciprocal Rank Fusion makes one list of them (ranks only, never scores). Each
channel (full text, concepts, vectors) carries the same total weight whatever
the number of its queries, so several wordings of one meaning do not inflate
one channel; a text that several channels agree on rises. The reranker, when
one is on, reorders the head of the fused list by reading the intent's own
sentence against each text; when it fails the fused order is kept and the
reason recorded. Nothing here is ever displayed; a result is ids, ranks, the
channels that found them and the query that ranked them best.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.ai.errors import AiCallError
from src.models import EmbeddedCorpus
from src.pipeline.insight.intents import IntentQueries
from src.retrieval.concepts import ConceptIndex
from src.retrieval.documents import RetrievalDocument, hadith_documents, quran_documents
from src.retrieval.fusion import FusedHit, fuse
from src.retrieval.lexical import Hit, search_lexical
from src.retrieval.query import query_terms
from src.retrieval.reranker import Reranker
from src.retrieval.vector import nearest

# Candidates each list returns, the fused candidates kept per intent and corpus, the head the
# reranker reads, and the texts the verifier judges. Starting values (the brief of 2026-10-05);
# tune them by `make eval`, not by taste.
SEARCH_TOP = 50
FUSED_TOP = 120
RERANK_TOP = 30
VERIFY_TOP = 12
CHANNEL_FTS = "fts"
CHANNEL_CONCEPTS = "concepts"
CHANNEL_VECTOR = "vector"


@dataclass(frozen=True, slots=True)
class Found:
    """A stored text a search found, with how it was found."""

    corpus: EmbeddedCorpus
    key: int
    retrieval_score: float
    retrieval_rank: int
    rerank_score: float | None
    matched_on: str
    # (list name, rank in that list) for every list that held the text.
    channels: tuple[tuple[str, int], ...]
    document: RetrievalDocument
    # The enriched Sunnah record this narration belongs to, when it is one of the file's.
    record: str | None = None

    def as_trace(self) -> dict[str, Any]:
        traced: dict[str, Any] = {
            "key": self.key,
            "rank": self.retrieval_rank,
            "rerank": self.rerank_score,
            "channels": [f"{name}@{rank}" for name, rank in self.channels],
        }
        if self.record is not None:
            traced["record"] = self.record
        return traced


@dataclass(frozen=True, slots=True)
class SearchResult:
    found: list[Found]
    rerank_error: str | None = None
    rerank_ms: int = 0
    rerank_model: str | None = None


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


def _one_per_record(fused: Sequence[FusedHit], records: Mapping[int, str]) -> list[FusedHit]:
    """Keep the best-ranked narration of each enriched record; texts of no record all stay."""
    seen: set[str] = set()
    kept: list[FusedHit] = []
    for hit in fused:
        record = records.get(hit.key)
        if record is not None:
            if record in seen:
                continue
            seen.add(record)
        kept.append(hit)
    return kept


def channel_weights(names: Sequence[str]) -> dict[str, float]:
    """Return a weight per channel so each channel's lists sum to one, whatever their number."""
    counts = Counter(name.split(":", 1)[0] for name in names)
    return {channel: 1.0 / count for channel, count in counts.items()}


def _matched_on(hit: FusedHit, queries: Mapping[str, str]) -> str:
    """Return the query of the list that ranked this text best."""
    best = min(hit.ranks, key=lambda item: item[1])[0]
    return queries.get(best, "")


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
        reranker: Reranker | None,
        concepts: Mapping[EmbeddedCorpus, ConceptIndex],
        rerank_top: int = RERANK_TOP,
        fused_top: int = FUSED_TOP,
    ) -> None:
        self._embedding = embedding
        self._reranker = reranker
        self._concepts = concepts
        self._rerank_top = rerank_top
        self._fused_top = fused_top

    async def search(
        self,
        session: AsyncSession,
        corpus: EmbeddedCorpus,
        queries: IntentQueries,
        vectors: Mapping[str, list[float]],
        *,
        pool: Collection[int] | None = None,
        records: Mapping[int, str] | None = None,
        exclude: Collection[int] = (),
    ) -> list[Found]:
        """
        Return the fused candidates of the intent's queries in `corpus`, best first.

        `pool` narrows every list to those texts; `records` names the enriched record of
        each narration, and the fused list then keeps one narration per record (the best
        ranked); `exclude` leaves out texts already judged (a widened search).
        """
        lists: dict[str, Sequence[Hit]] = {}
        texts: dict[str, str] = {}
        for index, query in enumerate(queries.lexical):
            terms = query_terms(query)
            lists[f"{CHANNEL_FTS}:{index}"] = await search_lexical(
                session, corpus, terms, limit=SEARCH_TOP, ids=pool
            )
            concepts = self._concepts[corpus].search(query, limit=SEARCH_TOP)
            if pool is not None:
                concepts = [hit for hit in concepts if hit.key in pool]
            lists[f"{CHANNEL_CONCEPTS}:{index}"] = concepts
            texts[f"{CHANNEL_FTS}:{index}"] = texts[f"{CHANNEL_CONCEPTS}:{index}"] = query
        for index, query in enumerate(queries.semantic):
            if query in vectors and self._embedding is not None:
                lists[f"{CHANNEL_VECTOR}:{index}"] = await nearest(
                    session,
                    corpus,
                    vectors[query],
                    model=self._embedding.model,
                    dimensions=len(vectors[query]),
                    limit=SEARCH_TOP,
                    ids=pool,
                )
                texts[f"{CHANNEL_VECTOR}:{index}"] = query
        fused = fuse(lists, weights=channel_weights(list(lists)))
        fused = _one_per_record([hit for hit in fused if hit.key not in exclude], records or {})[
            : self._fused_top
        ]
        if not fused:
            return []
        documents = await _documents(
            session, corpus, [hit.key for hit in fused], self._concepts[corpus]
        )
        return [
            Found(
                corpus,
                hit.key,
                hit.score,
                rank,
                None,
                _matched_on(hit, texts),
                hit.ranks,
                documents[hit.key],
                (records or {}).get(hit.key),
            )
            for rank, hit in enumerate(fused, start=1)
            if hit.key in documents
        ]

    async def rerank(self, query: str, found: list[Found]) -> SearchResult:
        """Reorder the head of `found` by the reranker reading `query`; keep the fused order on failure."""
        if self._reranker is None or not found or not query:
            return SearchResult(found)
        head, tail = found[: self._rerank_top], found[self._rerank_top :]
        outcome = await self._reranker.rerank(query, [item.document.body for item in head])
        if outcome.scores is None:
            return SearchResult(found, outcome.error, outcome.latency_ms)
        scored = [
            Found(
                item.corpus,
                item.key,
                item.retrieval_score,
                item.retrieval_rank,
                score,
                item.matched_on,
                item.channels,
                item.document,
                item.record,
            )
            for item, score in zip(head, outcome.scores, strict=True)
        ]
        # A stable sort keeps the fused order among equal reranker scores.
        scored.sort(key=lambda item: -(item.rerank_score or 0.0))
        return SearchResult(scored + tail, None, outcome.latency_ms, outcome.model)


def rerank_query(queries: IntentQueries, fallback: str) -> str:
    """Return the sentence the reranker reads: the intent's first semantic query, else its meaning."""
    return queries.semantic[0] if queries.semantic else fallback
