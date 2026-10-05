"""
Search the model-written concepts of the texts: verse annotations and Sunnah signals.

Each verse has annotations (key concepts, Arabic keywords, semantic tags) and
some hadiths have the signals of the enriched Sunnah file (key concepts, tags,
retrieval questions), all written by a language model in today's Arabic. They
are a ranking signal (master prompt v2 §9): a query stem found in a text's
concepts raises that text, weighted by how rare the stem is among all the
concepts, and a whole query word pair found in one concept raises it more. The
concepts are never shown and never stand in for the text.

The index is small (about 6,000 verses and 7,000 hadiths have concepts) and is
held in memory, built once per process from the database.
"""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import EmbeddedCorpus
from src.retrieval.documents import hadith_concepts, quran_documents
from src.retrieval.lexical import Hit
from src.retrieval.query import query_terms, stem
from src.scripture.text import search_copy

# The bonus of a concept that holds two query stems side by side.
PAIR_BONUS = 1.0


class ConceptIndex:
    """An inverted index from concept stems to the texts whose concepts hold them."""

    def __init__(self, corpus: EmbeddedCorpus, concepts: Mapping[int, Sequence[str]]) -> None:
        self.corpus = corpus
        # The concepts of each text, as given: a search's documents are built from them.
        self.concepts: dict[int, tuple[str, ...]] = {
            key: tuple(items) for key, items in concepts.items()
        }
        self._postings: dict[str, set[int]] = defaultdict(set)
        self._pairs: dict[tuple[str, str], set[int]] = defaultdict(set)
        for key, items in concepts.items():
            for concept in items:
                stems = [stem(word) for word in search_copy(concept).lower().split()]
                for word in stems:
                    self._postings[word].add(key)
                for pair in pairwise(stems):
                    self._pairs[pair].add(key)
        self._documents = len(concepts)
        self._vocabulary = sorted(self._postings)

    def __len__(self) -> int:
        return self._documents

    def _expand(self, term: str) -> list[str]:
        """Return the concept stems that begin with `term` (the stem itself included)."""
        return [word for word in self._vocabulary if word.startswith(term)]

    def _idf(self, keys: set[int]) -> float:
        return math.log(1.0 + (self._documents - len(keys) + 0.5) / (len(keys) + 0.5))

    def search(self, text: str, *, limit: int = 30) -> list[Hit]:
        """Return the texts whose concepts hold the query's stems, best first."""
        terms = query_terms(text)
        scores: dict[int, float] = defaultdict(float)
        expanded: dict[str, list[str]] = {term: self._expand(term) for term in terms}
        for words in expanded.values():
            keys = set().union(*(self._postings[word] for word in words)) if words else set()
            weight = self._idf(keys) if keys else 0.0
            for key in keys:
                scores[key] += weight
        for first, second in pairwise(terms):
            for left in expanded[first]:
                for right in expanded[second]:
                    for key in self._pairs.get((left, right), ()):
                        scores[key] += PAIR_BONUS
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [Hit(key, score) for key, score in ranked[:limit]]


async def load_concept_index(
    session: AsyncSession, corpus: EmbeddedCorpus, *, collections: Sequence[str] | None = None
) -> ConceptIndex:
    """
    Build the index of a corpus from the stored annotations or signals.

    The stemming of every concept takes seconds of pure Python: it runs in a thread so the
    event loop keeps serving (in the scan worker, a loop held that long made its queue
    connection time out and the worker stop).
    """
    if corpus is EmbeddedCorpus.QURAN:
        documents = await quran_documents(session)
        concepts = {doc.key: doc.concepts for doc in documents if doc.concepts}
    else:
        concepts = await hadith_concepts(session, collections=collections)
    return await asyncio.to_thread(ConceptIndex, corpus, concepts)
