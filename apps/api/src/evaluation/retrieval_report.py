"""Write the retrieval section of docs/BENCHMARK.md from a retrieval benchmark result."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from string import Template

from src.evaluation.retrieval_benchmark import (
    LatencyStat,
    MethodScore,
    QueryRanks,
    RetrievalBenchmarkResult,
)

SECTION = "retrieval"
TEMPLATE = Template(
    Path(__file__).with_name("retrieval_report_template.txt").read_text(encoding="utf-8")
)
LLM_PREFIX = "llm-"


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _score_row(item: MethodScore) -> list[str]:
    return [
        f"`{item.method}`",
        item.corpus,
        _pct(item.recall_at_1),
        _pct(item.recall_at_3),
        _pct(item.recall_at_10),
        _pct(item.recall_at_30),
        f"{item.mrr_at_10:.3f}",
    ]


def _latency_row(item: LatencyStat) -> list[str]:
    return [item.name, str(item.samples), f"{item.p50_ms:.0f} ms", f"{item.p95_ms:.0f} ms"]


def best(scores: Sequence[MethodScore], prefix: str) -> MethodScore | None:
    """Return the method of `prefix` with the best MRR@10 over all queries."""
    candidates = [
        item for item in scores if item.corpus == "all" and item.method.startswith(prefix)
    ]
    return max(candidates, key=lambda item: (item.mrr_at_10, item.recall_at_10), default=None)


def merge(
    previous: RetrievalBenchmarkResult, latest: RetrievalBenchmarkResult
) -> RetrievalBenchmarkResult:
    """Keep every method of `previous` that `latest` did not measure again."""
    methods = {item.method for item in latest.scores}
    latencies = {item.name for item in latest.latencies}
    ranks = {item.id: item for item in previous.per_query}
    per_query = [
        QueryRanks(
            id=item.id,
            corpus=item.corpus,
            ranks={
                **{k: v for k, v in ranks.get(item.id, item).ranks.items() if k not in methods},
                **item.ranks,
            },
        )
        for item in latest.per_query
    ]
    return latest.model_copy(
        update={
            "scores": [item for item in previous.scores if item.method not in methods]
            + latest.scores,
            "latencies": [item for item in previous.latencies if item.name not in latencies]
            + latest.latencies,
            "per_query": per_query,
            "cells": list({cell.name: cell for cell in [*previous.cells, *latest.cells]}.values()),
            "rerank_cell": latest.rerank_cell or previous.rerank_cell,
            "cost_usd": round(previous.cost_usd + latest.cost_usd, 6),
        }
    )


def recommendations(result: RetrievalBenchmarkResult) -> list[list[str]]:
    rows: list[list[str]] = []
    for provider in sorted({cell.provider for cell in result.cells}):
        names = [cell.name for cell in result.cells if cell.provider is provider]
        found = [best(result.scores, f"vector:{name}") for name in names]
        chosen = max((item for item in found if item is not None), key=lambda item: item.mrr_at_10)
        cell = next(cell for cell in result.cells if f"vector:{cell.name}" == chosen.method)
        rows.append(
            [
                f"embedding ({provider.value})",
                f"`{cell.model}` @ {cell.dimensions}",
                f"MRR@10 {chosen.mrr_at_10:.3f}, recall@10 {_pct(chosen.recall_at_10)}",
            ]
        )
    lexical = [
        item for item in (best(result.scores, "fts"), best(result.scores, "trigram")) if item
    ]
    if lexical:
        winner = max(lexical, key=lambda item: item.mrr_at_10)
        rows.append(["lexical search", f"`{winner.method}`", f"MRR@10 {winner.mrr_at_10:.3f}"])
    cross = [
        item
        for item in result.scores
        if item.corpus == "all"
        and item.method.startswith("rerank:")
        and not item.method.startswith(f"rerank:{LLM_PREFIX}")
    ]
    if cross:
        winner = max(cross, key=lambda item: (item.mrr_at_10, item.recall_at_3))
        rows.append(
            [
                "reranker",
                f"`{winner.method.removeprefix('rerank:')}`",
                f"MRR@10 {winner.mrr_at_10:.3f}, recall@3 {_pct(winner.recall_at_3)}",
            ]
        )
    return rows


def render(result: RetrievalBenchmarkResult, raw_path: str, gold_path: str) -> str:
    """Return the Markdown of the retrieval section."""
    overall = sorted(
        (item for item in result.scores if item.corpus == "all"),
        key=lambda item: -item.mrr_at_10,
    )
    by_corpus = sorted(
        (item for item in result.scores if item.corpus != "all"),
        key=lambda item: (item.corpus, -item.mrr_at_10),
    )
    header = ["Method", "Corpus", "R@1", "R@3", "R@10", "R@30", "MRR@10"]
    quran = sum(1 for item in result.per_query if item.corpus == "quran")
    return TEMPLATE.substitute(
        date=f"{result.started_at:%d %B %Y}",
        raw_path=raw_path,
        gold_path=gold_path,
        queries=result.queries,
        quran_queries=quran,
        hadith_queries=result.queries - quran,
        collections=", ".join(result.hadith_collections),
        rerank_cell=result.rerank_cell or "none",
        cells_table=_table(
            ["Cell", "Provider", "Model", "Dimensions"],
            (
                [f"`{c.name}`", c.provider.value, f"`{c.model}`", str(c.dimensions)]
                for c in result.cells
            ),
        ),
        overall_table=_table(header, (_score_row(item) for item in overall)),
        corpus_table=_table(header, (_score_row(item) for item in by_corpus)),
        latency_table=_table(
            ["Step", "Samples", "p50", "p95"], (_latency_row(item) for item in result.latencies)
        ),
        choices_table=_table(["Setting", "Choice", "Measured"], recommendations(result)),
        cost=f"{result.cost_usd:.4f}",
    )
