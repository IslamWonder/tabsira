"""
Embed the scripture store for semantic search.

    uv run python -m src.cli.embed_corpus [quran] [hadith] [--provider P] [--model M]
        [--dimensions N] [--collections a,b] [--batch-size N] [--concurrency N]
        [--max-cost USD] [--dry-run]

With no corpus, both. The provider, model and size default to the active
provider's `embedding_model` and `embedding_dimensions` (docs/BENCHMARK.md says
why). Only documents that are new or changed since their vector was made are
sent, so a second run sends nothing; a run that stopped resumes where it
stopped. `--max-cost` stops a run once it has spent that much (what it
finished is kept). `--dry-run` counts what would be sent and calls nothing.

When the provider has no API key or no embedding model, nothing is embedded
and the command says so and exits 0: `make data` still builds everything else,
and search falls back to its lexical half. Exit 1 when a run fails.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ai.client import ModelClient, client_for
from src.ai.errors import AiCallError
from src.config import AiProvider, Settings, get_settings
from src.database import dispose_engine, get_sessionmaker
from src.models import EmbeddedCorpus
from src.retrieval.documents import hadith_documents, quran_documents
from src.retrieval.embedding_store import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    CorpusEmbedder,
    RunReport,
    SpendCapReachedError,
    stored_hashes,
)


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Embed the scripture store for semantic search.")
    parser.add_argument(
        "corpora", nargs="*", metavar="CORPUS", help="quran, hadith (default: both)"
    )
    parser.add_argument("--provider", choices=[p.value for p in AiProvider])
    parser.add_argument("--model")
    parser.add_argument("--dimensions", type=int)
    parser.add_argument("--collections", help="hadith books, comma separated (default: all)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--max-cost", type=float, help="stop once this many US dollars are spent")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _describe(report: RunReport) -> str:
    return (
        f"{report.corpus.value}: {report.model} ({report.dimensions or 'native'} dims), "
        f"{report.documents} documents, {report.unchanged} unchanged, {report.embedded} embedded "
        f"in {report.batches} batches, {report.input_tokens} tokens, ${report.cost_usd:.4f}"
    )


async def run(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    client: ModelClient | None = None,
) -> int:
    """Run the command; return the process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    unknown = sorted(set(args.corpora) - {corpus.value for corpus in EmbeddedCorpus})
    if unknown:
        parser.error(f"unknown corpus {', '.join(unknown)}; the corpora are quran and hadith")
    settings = settings or get_settings()
    provider = AiProvider(args.provider) if args.provider else settings.ai_provider
    block = settings.ai_ovh if provider is AiProvider.OVH else settings.ai_openai
    model = args.model or block.embedding_model
    dimensions = args.dimensions if args.dimensions is not None else block.embedding_dimensions
    if not model or not (client or block.api_key.get_secret_value()):
        _say(f"embeddings skipped: {provider.value} has no embedding model or no API key set")
        return 0
    corpora = [EmbeddedCorpus(name) for name in args.corpora] or list(EmbeddedCorpus)
    collections = args.collections.split(",") if args.collections else None
    maker = sessionmaker or get_sessionmaker()
    try:
        async with httpx.AsyncClient() as http:
            embedder = CorpusEmbedder(
                maker,
                client or client_for(settings, http, provider=provider),
                model=model,
                dimensions=dimensions,
                batch_size=args.batch_size,
                concurrency=args.concurrency,
                max_cost_usd=args.max_cost,
            )
            for corpus in corpora:
                async with maker() as session:
                    documents = (
                        await quran_documents(session)
                        if corpus is EmbeddedCorpus.QURAN
                        else await hadith_documents(session, collections=collections)
                    )
                    if args.dry_run:
                        known = await stored_hashes(session, corpus, model, dimensions)
                        todo = [doc for doc in documents if known.get(doc.key) != doc.sha256]
                        characters = sum(len(doc.body) for doc in todo)
                        _say(
                            f"{corpus.value}: {len(documents)} documents, {len(todo)} to embed, "
                            f"{characters} characters (dry run, nothing sent)"
                        )
                        continue
                _say(_describe(await embedder.run(corpus, documents)))
    except (AiCallError, SpendCapReachedError, SQLAlchemyError, OSError) as error:
        # A database that times out or goes away fails the run like the provider would.
        sys.stderr.write(f"embedding failed: {type(error).__name__}: {error}\n")
        return 1
    finally:
        if sessionmaker is None:
            await dispose_engine()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # One line per HTTP request would bury the report.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
