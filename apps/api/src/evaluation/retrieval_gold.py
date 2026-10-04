"""
The retrieval gold set: concept queries and the stored texts that answer them.

`tests/evaluation/retrieval/gold.json` holds Arabic concept queries written
the way the insight planner writes them, each with the references that answer
it (`Q:30:50`, `Q:3:190-191`, `H:bukhari:1032` in the stored numbering). The
references are resolved to verse and hadith ids before a run; a reference that
names nothing stored stops the run, since a gold answer that cannot be found
would count as a miss of every method alike.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EmbeddedCorpus
from src.retrieval.refs import resolve_hadiths, resolve_verses

RETRIEVAL_GOLD = (
    Path(__file__).resolve().parents[2] / "tests" / "evaluation" / "retrieval" / "gold.json"
)


class GoldQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    corpus: Literal["quran", "hadith"]
    query: Annotated[str, Field(min_length=2)]
    relevant: Annotated[list[str], Field(min_length=1)]
    source: str


class RetrievalGold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    description: str
    # The books the hadith queries are judged against; a run searches these only.
    hadith_collections: list[str]
    queries: list[GoldQuery]


class GoldError(ValueError):
    """The gold set names a text that is not stored, or is malformed."""


class ResolvedQuery(BaseModel):
    """A gold query with its answers as stored ids."""

    model_config = ConfigDict(frozen=True)

    id: str
    corpus: EmbeddedCorpus
    query: str
    relevant_ids: frozenset[int]


def load_retrieval_gold(path: Path = RETRIEVAL_GOLD) -> RetrievalGold:
    gold = RetrievalGold.model_validate(json.loads(path.read_text(encoding="utf-8")))
    ids = [query.id for query in gold.queries]
    if len(ids) != len(set(ids)):
        message = "the retrieval gold set has a query id twice"
        raise GoldError(message)
    return gold


async def resolve_gold(session: AsyncSession, gold: RetrievalGold) -> list[ResolvedQuery]:
    """Return every query with its answers resolved to ids; raise when one is not stored."""
    quran_keys = {key for q in gold.queries if q.corpus == "quran" for key in q.relevant}
    hadith_keys = {key for q in gold.queries if q.corpus == "hadith" for key in q.relevant}
    found = await resolve_verses(session, quran_keys) | await resolve_hadiths(session, hadith_keys)
    missing = sorted(key for key, ids in found.items() if not ids)
    if missing:
        message = f"the gold set names texts that are not stored: {', '.join(missing)}"
        raise GoldError(message)
    return [
        ResolvedQuery(
            id=query.id,
            corpus=EmbeddedCorpus(query.corpus),
            query=query.query,
            relevant_ids=frozenset(item for key in query.relevant for item in found[key]),
        )
        for query in gold.queries
    ]
