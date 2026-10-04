"""
Measure retrieval on the gold set: embeddings, lexical search, fusion and rerankers.

    uv run python -m src.cli.retrieval_benchmark [--cells a,b] [--lexical fts,trigram]
        [--reranker NAME=URL ...] [--llm-rerank MODEL ...] [--rerank-cell CELL] [--no-report]

The corpus vectors of every cell must exist (`src.cli.embed_corpus`). Each
`--reranker` is a running services/vision whose `POST /rerank` serves one
cross-encoder; run the command once per cross-encoder to keep one model in
memory at a time: the results of a day are merged, method by method, in
`tests/evaluation/results/retrieval-<date>.json` (not committed), and the
retrieval section of docs/BENCHMARK.md is rewritten from the merged result.
`--llm-rerank` adds a chat model of the active provider as the baseline.
Calls cost money: the query embeddings (a fraction of a cent) and the LLM
rerank (about $0.15 for gpt-5.4-nano over the gold set). Exit 0, or 1 when a
reranker did not answer.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.client import ModelClient, client_for
from src.ai.records import CallLog
from src.config import AiProvider, Settings, get_settings
from src.database import dispose_engine, get_sessionmaker
from src.evaluation.report_sections import replace_section
from src.evaluation.retrieval_benchmark import (
    EmbeddingCell,
    Reranker,
    RetrievalBenchmarkResult,
    run_retrieval_benchmark,
)
from src.evaluation.retrieval_gold import RETRIEVAL_GOLD, load_retrieval_gold, resolve_gold
from src.evaluation.retrieval_report import LLM_PREFIX, SECTION, merge, render
from src.models import EmbeddedCorpus
from src.retrieval.concepts import load_concept_index
from src.retrieval.lexical import LexicalMethod
from src.retrieval.reranker import RerankerClient, llm_rerank

API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parents[1]
RESULTS_DIR = API_DIR / "tests" / "evaluation" / "results"
REPORT_PATH = REPO_ROOT / "docs" / "BENCHMARK.md"
RERANK_TIMEOUT_SECONDS = 120.0
# The embedding the pipeline uses (docs/BENCHMARK.md): its candidates are the ones reranked.
DEFAULT_RERANK_CELL = "openai-3-large"

CELLS = (
    EmbeddingCell(
        name="openai-3-small",
        provider=AiProvider.OPENAI,
        model="text-embedding-3-small",
        dimensions=1536,
    ),
    EmbeddingCell(
        name="openai-3-large",
        provider=AiProvider.OPENAI,
        model="text-embedding-3-large",
        dimensions=1536,
    ),
    EmbeddingCell(name="ovh-bge-m3", provider=AiProvider.OVH, model="bge-m3", dimensions=1024),
)


class RerankerDownError(RuntimeError):
    """A cross-encoder of the benchmark did not answer; its numbers would be the fused order's."""


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure retrieval on the gold set.")
    parser.add_argument("--cells", default=",".join(cell.name for cell in CELLS))
    parser.add_argument("--lexical", default="fts,trigram")
    parser.add_argument("--reranker", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--llm-rerank", action="append", default=[], metavar="MODEL")
    parser.add_argument("--rerank-cell", help="the cell whose fused candidates are reranked")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--gold", type=Path, default=RETRIEVAL_GOLD, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    known = {cell.name for cell in CELLS}
    args.cells = [name for name in args.cells.split(",") if name]
    if unknown := sorted(set(args.cells) - known):
        parser.error(f"unknown cell {', '.join(unknown)}; the cells are {', '.join(sorted(known))}")
    if args.rerank_cell is None:
        args.rerank_cell = (
            DEFAULT_RERANK_CELL if DEFAULT_RERANK_CELL in args.cells else args.cells[0]
        )
    elif args.rerank_cell not in args.cells:
        parser.error(f"--rerank-cell {args.rerank_cell} is not one of the cells measured")
    args.lexical = [LexicalMethod(name) for name in args.lexical.split(",") if name]
    pairs = [value.split("=", 1) for value in args.reranker]
    if any(len(pair) != 2 for pair in pairs):
        parser.error("--reranker takes NAME=URL")
    args.reranker = dict(pairs)
    return args


def cross_encoder(client: RerankerClient) -> Reranker:
    async def rerank(query: str, passages: Sequence[str]) -> list[float]:
        outcome = await client.rerank(query, passages)
        if outcome.scores is None:
            raise RerankerDownError(outcome.error or "no scores")
        return outcome.scores

    return rerank


def language_model(client: ModelClient, model: str) -> Reranker:
    async def rerank(query: str, passages: Sequence[str]) -> list[float]:
        return await llm_rerank(client, query, passages, model=model)

    return rerank


def write_outputs(result: RetrievalBenchmarkResult, args: argparse.Namespace) -> list[Path]:
    """Merge with the day's earlier result, write it, and rewrite the report section."""
    args.results_dir.mkdir(parents=True, exist_ok=True)
    raw = args.results_dir / f"retrieval-{result.started_at:%Y-%m-%d}.json"
    if raw.is_file():
        result = merge(RetrievalBenchmarkResult.model_validate_json(raw.read_text()), result)
    raw.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    written = [raw]
    if not args.no_report:
        current = args.report.read_text(encoding="utf-8") if args.report.is_file() else ""
        section = render(result, _relative(raw), _relative(args.gold))
        args.report.write_text(replace_section(current, SECTION, section), encoding="utf-8")
        written.append(args.report)
    return written


async def run(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    clients: dict[AiProvider, ModelClient] | None = None,
    http: httpx.AsyncClient | None = None,
) -> int:
    """Run the benchmark; return the process exit code."""
    args = parse_args(argv)
    settings = settings or get_settings()
    gold = load_retrieval_gold(args.gold)
    log = CallLog()
    maker = sessionmaker or get_sessionmaker()
    try:
        async with http or httpx.AsyncClient() as transport, maker() as session:
            made = clients or {
                provider: client_for(settings, transport, provider=provider, log=log)
                for provider in AiProvider
            }
            rerankers: dict[str, Reranker] = {
                name: cross_encoder(
                    RerankerClient(url, transport, timeout_seconds=RERANK_TIMEOUT_SECONDS)
                )
                for name, url in args.reranker.items()
            }
            rerankers |= {
                f"{LLM_PREFIX}{model}": language_model(made[settings.ai_provider], model)
                for model in args.llm_rerank
            }
            concepts = {
                EmbeddedCorpus.QURAN: await load_concept_index(session, EmbeddedCorpus.QURAN),
                EmbeddedCorpus.HADITH: await load_concept_index(
                    session, EmbeddedCorpus.HADITH, collections=gold.hadith_collections
                ),
            }
            result = await run_retrieval_benchmark(
                session,
                await resolve_gold(session, gold),
                cells=[cell for cell in CELLS if cell.name in args.cells],
                clients=made,
                concepts=concepts,
                hadith_collections=gold.hadith_collections,
                lexical_methods=args.lexical,
                rerankers=rerankers,
                rerank_cell=args.rerank_cell,
            )
    except RerankerDownError as error:
        sys.stderr.write(f"a reranker did not answer: {error}\n")
        return 1
    finally:
        if sessionmaker is None:
            await dispose_engine()
    result = result.model_copy(update={"cost_usd": round(result.cost_usd + log.total_cost_usd, 6)})
    for path in write_outputs(result, args):
        _say(f"wrote {_relative(path)}")
    _say(f"spend: ${result.cost_usd:.4f} at {datetime.now(UTC):%H:%M} UTC")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
