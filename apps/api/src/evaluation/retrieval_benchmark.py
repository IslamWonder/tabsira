"""
The retrieval benchmark: which embedding, which lexical search, which fusion, which reranker.

Every query of the retrieval gold set is run through each method on its own
corpus (Quran, or the hadith books the gold set names), and the stored answers
are looked for in the top 30:

- `vector:<cell>`: nearest documents under one embedding model and size;
- `fts` and `trigram`: the two lexical searches of `src.retrieval.lexical`;
- `concepts`: the model-written concepts (`src.retrieval.concepts`);
- `hybrid:<cell>`: vector and full text fused by RRF;
- `hybrid+concepts:<cell>`: the same with the concepts as a third list;
- `rerank:<name>`: the 30 fused candidates of the rerank cell, reordered by a
  reranker (a cross-encoder of services/vision, or a chat model);
- `rerank:<name>+metadata`: the reference recipe of the earlier build
  (`cross_encoder_reranker.py`): 0.6 x (0.7 x reranker + 0.3 x share of the
  query's stems found in the text's concepts) + 0.4 x fused score.

Recall@k is the share of queries with an answer in the first k, MRR@10 the
mean of 1/rank of the first answer (0 past ten). Latency is the wall time of
each search and rerank on this machine, and of embedding one query at the
provider.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.client import ModelClient
from src.config import AiProvider
from src.evaluation.retrieval_gold import ResolvedQuery
from src.models import EmbeddedCorpus
from src.retrieval.concepts import ConceptIndex
from src.retrieval.documents import RetrievalDocument, hadith_documents, quran_documents
from src.retrieval.embedding_store import batch_limit, batches
from src.retrieval.fusion import FusedHit, fuse
from src.retrieval.lexical import Hit, LexicalMethod, search_lexical
from src.retrieval.query import query_terms, stem
from src.retrieval.vector import nearest
from src.scripture.text import search_copy

TOP = 30
CUTOFFS = (1, 3, 10)
# Single-query embedding calls timed per cell, as a scan makes them.
LATENCY_PROBES = 5

# Scores the passages of one query, in order, from 0 to 1.
Reranker = Callable[[str, Sequence[str]], Awaitable[list[float]]]


class EmbeddingCell(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    provider: AiProvider
    model: str
    dimensions: int


class MethodScore(BaseModel):
    method: str
    corpus: str
    queries: int
    recall_at_1: float
    recall_at_3: float
    recall_at_10: float
    recall_at_30: float
    mrr_at_10: float


class LatencyStat(BaseModel):
    name: str
    samples: int
    p50_ms: float
    p95_ms: float


class QueryRanks(BaseModel):
    """Where the first answer of one query came in each method (None: not in the top 30)."""

    id: str
    corpus: str
    ranks: dict[str, int | None]


class RetrievalBenchmarkResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    queries: int
    hadith_collections: list[str]
    cells: list[EmbeddingCell]
    rerank_cell: str | None
    scores: list[MethodScore]
    latencies: list[LatencyStat]
    per_query: list[QueryRanks]
    cost_usd: float


def first_rank(keys: Sequence[int], relevant: frozenset[int]) -> int | None:
    return next((index for index, key in enumerate(keys, start=1) if key in relevant), None)


def score(method: str, corpus: str, ranks: Sequence[int | None]) -> MethodScore:
    count = len(ranks) or 1
    found = [rank for rank in ranks if rank is not None]
    recall = {cutoff: sum(1 for rank in found if rank <= cutoff) / count for cutoff in CUTOFFS}
    return MethodScore(
        method=method,
        corpus=corpus,
        queries=len(ranks),
        recall_at_1=recall[1],
        recall_at_3=recall[3],
        recall_at_10=recall[10],
        recall_at_30=len(found) / count,
        mrr_at_10=sum(1 / rank for rank in found if rank <= CUTOFFS[-1]) / count,
    )


def percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def latency(name: str, seconds: Sequence[float]) -> LatencyStat:
    milliseconds = [value * 1000 for value in seconds] or [0.0]
    return LatencyStat(
        name=name,
        samples=len(seconds),
        p50_ms=round(statistics.median(milliseconds), 1),
        p95_ms=round(percentile(milliseconds, 0.95), 1),
    )


async def timed[T](awaitable: Awaitable[T], sink: list[float]) -> T:
    """Await `awaitable` and append its wall time, in seconds, to `sink`."""
    started = time.perf_counter()
    value = await awaitable
    sink.append(time.perf_counter() - started)
    return value


def asked_dimensions(cell: EmbeddingCell) -> int | None:
    """Return the `dimensions` to send: none for OVH, whose bge-m3 has one size and takes none."""
    return cell.dimensions if cell.provider is AiProvider.OPENAI else None


async def embed_queries(
    client: ModelClient, cell: EmbeddingCell, texts: Sequence[str]
) -> tuple[list[list[float]], float, list[float]]:
    """Embed every query in batches, then time a few one-query calls; return vectors, cost, times."""
    vectors: list[list[float]] = []
    cost = 0.0
    for batch in batches(texts, batch_limit(cell.provider)):
        result = await client.embed(batch, model=cell.model, dimensions=asked_dimensions(cell))
        vectors += result.vectors
        cost += result.record.cost_usd or 0.0
    probes: list[float] = []
    for text in texts[:LATENCY_PROBES]:
        result = await client.embed([text], model=cell.model, dimensions=asked_dimensions(cell))
        probes.append(result.record.latency_ms / 1000)
        cost += result.record.cost_usd or 0.0
    return vectors, cost, probes


def fusions(
    lists: Mapping[str, Sequence[Hit]], cells: Sequence[EmbeddingCell]
) -> dict[str, list[FusedHit]]:
    """Return the fused rankings of every cell: with full text, and with the concepts too."""
    fused: dict[str, list[FusedHit]] = {}
    for cell in cells:
        vector = lists[f"vector:{cell.name}"]
        both = fuse({"vector": vector, "fts": lists["fts"]})
        fused[f"hybrid:{cell.name}"] = both[:TOP]
        three = fuse({"vector": vector, "fts": lists["fts"], "concepts": lists["concepts"]})
        fused[f"hybrid+concepts:{cell.name}"] = three[:TOP]
    return fused


def concept_overlap(query: str, document: RetrievalDocument) -> float:
    """Return the share of the query's stems that begin a stem of the document's concepts."""
    terms = query_terms(query)
    stems = {stem(word) for concept in document.concepts for word in search_copy(concept).split()}
    found = sum(1 for term in terms if any(word.startswith(term) for word in stems))
    return found / len(terms) if terms else 0.0


def reference_blend(model: float, overlap: float, fused: float) -> float:
    """Return the earlier build's blend: 0.6 x (0.7 x model + 0.3 x metadata) + 0.4 x fused."""
    return 0.6 * (0.7 * model + 0.3 * overlap) + 0.4 * fused


async def candidate_documents(
    session: AsyncSession, corpus: EmbeddedCorpus, keys: Sequence[int]
) -> list[RetrievalDocument]:
    """Return the documents of `keys`, in the order of `keys`."""
    found = (
        await quran_documents(session, list(keys))
        if corpus is EmbeddedCorpus.QURAN
        else await hadith_documents(session, hadith_ids=list(keys))
    )
    by_key = {document.key: document for document in found}
    return [by_key[key] for key in keys if key in by_key]


async def reranked(
    query: str,
    candidates: Sequence[FusedHit],
    documents: Sequence[RetrievalDocument],
    rerankers: Mapping[str, Reranker],
    times: dict[str, list[float]],
) -> dict[str, list[int]]:
    """Reorder the fused candidates by each reranker, alone and in the reference blend."""
    keys = [document.key for document in documents]
    top = max((hit.score for hit in candidates), default=1.0) or 1.0
    fused = {hit.key: hit.score / top for hit in candidates}
    overlap = {document.key: concept_overlap(query, document) for document in documents}
    orders: dict[str, list[int]] = {}
    for name, rerank in rerankers.items():
        scores = await timed(
            rerank(query, [document.body for document in documents]),
            times.setdefault(f"rerank 30: {name}", []),
        )
        by_key = dict(zip(keys, scores, strict=True))
        orders[f"rerank:{name}"] = sorted(keys, key=lambda key: -by_key[key])
        blend = {
            key: reference_blend(by_key[key], overlap[key], fused.get(key, 0.0)) for key in keys
        }
        orders[f"rerank:{name}+metadata"] = sorted(keys, key=lambda key: -blend[key])
    return orders


async def run_retrieval_benchmark(
    session: AsyncSession,
    queries: Sequence[ResolvedQuery],
    *,
    cells: Sequence[EmbeddingCell],
    clients: Mapping[AiProvider, ModelClient],
    concepts: Mapping[EmbeddedCorpus, ConceptIndex],
    hadith_collections: Sequence[str],
    lexical_methods: Sequence[LexicalMethod] = tuple(LexicalMethod),
    rerankers: Mapping[str, Reranker] | None = None,
    rerank_cell: str | None = None,
) -> RetrievalBenchmarkResult:
    """Run every method on every query; return scores, latencies and per-query ranks."""
    started_at = datetime.now(UTC)
    texts = [query.query for query in queries]
    vectors: dict[str, list[list[float]]] = {}
    times: dict[str, list[float]] = {}
    cost = 0.0
    for cell in cells:
        vectors[cell.name], spent, probes = await embed_queries(clients[cell.provider], cell, texts)
        cost += spent
        times[f"embed one query: {cell.name}"] = probes
    per_query: list[QueryRanks] = []
    for index, query in enumerate(queries):
        scope = list(hadith_collections) if query.corpus is EmbeddedCorpus.HADITH else None
        terms = query_terms(query.query)
        lists: dict[str, Sequence[Hit]] = {}
        for method in [
            LexicalMethod.FTS,
            *(m for m in lexical_methods if m is not LexicalMethod.FTS),
        ]:
            lists[method.value] = await timed(
                search_lexical(
                    session, query.corpus, terms, method=method, limit=TOP, collections=scope
                ),
                times.setdefault(f"search: {method.value}", []),
            )
        started = time.perf_counter()
        lists["concepts"] = concepts[query.corpus].search(query.query, limit=TOP)
        times.setdefault("search: concepts", []).append(time.perf_counter() - started)
        for cell in cells:
            lists[f"vector:{cell.name}"] = await timed(
                nearest(
                    session,
                    query.corpus,
                    vectors[cell.name][index],
                    model=cell.model,
                    dimensions=cell.dimensions,
                    limit=TOP,
                    collections=scope,
                ),
                times.setdefault(f"search: vector {cell.name}", []),
            )
        fused = fusions(lists, cells)
        rankings = {name: [hit.key for hit in hits] for name, hits in lists.items()}
        rankings |= {name: [hit.key for hit in hits] for name, hits in fused.items()}
        if rerankers:
            candidates = fused[f"hybrid+concepts:{rerank_cell}"]
            documents = await candidate_documents(
                session, query.corpus, [hit.key for hit in candidates]
            )
            rankings |= await reranked(query.query, candidates, documents, rerankers, times)
        per_query.append(
            QueryRanks(
                id=query.id,
                corpus=query.corpus.value,
                ranks={
                    name: first_rank(keys, query.relevant_ids) for name, keys in rankings.items()
                },
            )
        )
    methods = list(per_query[0].ranks) if per_query else []
    scores = [
        score(
            method,
            corpus,
            [item.ranks[method] for item in per_query if corpus in {"all", item.corpus}],
        )
        for method in methods
        for corpus in ("quran", "hadith", "all")
    ]
    return RetrievalBenchmarkResult(
        started_at=started_at,
        finished_at=datetime.now(UTC),
        queries=len(queries),
        hadith_collections=list(hadith_collections),
        cells=list(cells),
        rerank_cell=rerank_cell if rerankers else None,
        scores=scores,
        latencies=[latency(name, values) for name, values in times.items()],
        per_query=per_query,
        cost_usd=round(cost, 6),
    )
