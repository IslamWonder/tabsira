"""
Retrieval documents: what is embedded, searched and reranked for a verse or a hadith.

A document is the folded search copy of a text, never its displayed form,
followed by the model-written concepts that describe it: the annotations of a
verse (`quran_annotations`), the signals of a hadith (`hadith_signals`). The
concepts let a query written in today's Arabic («إحياء الأرض بالمطر») find a
text written fourteen centuries ago; they rank, they are never shown, and the
document as a whole is never shown either (master prompt v2 §9).

For a hadith, the chain of narrators is left out when the text says plainly
where it ends (`src.scripture.spans`): names carry no meaning to match and cost
tokens. A document is capped in length; the cap keeps the start of the text,
where a hadith's subject usually is.

A signal record is linked to every hadith its narration matched
(`hadith_signals.matches`), so the parallel narrations of one hadith in
several books share its concepts.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    EmbeddedCorpus,
    Hadith,
    HadithSignal,
    QuranAnnotation,
    QuranVerse,
    QuranVerseSearch,
)
from src.scripture.spans import SpanRole, hadith_spans
from src.scripture.text import search_copy

# Characters of folded text kept in a document, and of concepts after it.
TEXT_MAX_CHARS = 1200
CONCEPTS_MAX_CHARS = 500
CONCEPT_SEPARATOR = "، "
TEXT_CONCEPT_SEPARATOR = " | "
# Questions of the enriched Sunnah file kept per hadith: the first are the closest to the text.
TOPICS_PER_SIGNAL = 3


@dataclass(frozen=True, slots=True)
class RetrievalDocument:
    """The document of one stored text: `key` is the verse or hadith id."""

    corpus: EmbeddedCorpus
    key: int
    text: str
    concepts: tuple[str, ...]

    @property
    def body(self) -> str:
        """Text and concepts together, as embedded and reranked."""
        if not self.concepts:
            return self.text
        concepts = _clip(CONCEPT_SEPARATOR.join(self.concepts), CONCEPTS_MAX_CHARS)
        return f"{self.text}{TEXT_CONCEPT_SEPARATOR}{concepts}"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


def _clip(text: str, limit: int) -> str:
    """Cut `text` at a word boundary within `limit` characters."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return cut[:space] if space > 0 else cut


def unique_concepts(groups: Iterable[Iterable[str]]) -> tuple[str, ...]:
    """Join concept lists in order, dropping blanks and repeats (compared folded)."""
    seen: set[str] = set()
    kept: list[str] = []
    for group in groups:
        for concept in group:
            folded = search_copy(concept)
            if folded and folded not in seen:
                seen.add(folded)
                kept.append(concept.strip())
    return tuple(kept)


def verse_document(verse_id: int, folded_text: str, concepts: Sequence[str]) -> RetrievalDocument:
    return RetrievalDocument(
        EmbeddedCorpus.QURAN, verse_id, _clip(folded_text, TEXT_MAX_CHARS), tuple(concepts)
    )


def hadith_body(text: str) -> str:
    """Return the folded text of a hadith from the end of its chain, or all of it."""
    spans = hadith_spans(text)
    start = spans[1].start if spans[0].role is SpanRole.CHAIN else 0
    return search_copy(text[start:])


def hadith_document(hadith_id: int, text: str, concepts: Sequence[str]) -> RetrievalDocument:
    return RetrievalDocument(
        EmbeddedCorpus.HADITH, hadith_id, _clip(hadith_body(text), TEXT_MAX_CHARS), tuple(concepts)
    )


def annotation_concepts(annotation: QuranAnnotation) -> tuple[str, ...]:
    return unique_concepts(
        [annotation.key_concepts, annotation.keywords_ar, annotation.semantic_tags]
    )


def signal_concepts(signal: HadithSignal) -> list[list[str]]:
    return [
        signal.key_concepts,
        signal.semantic_tags,
        signal.topics_for_retrieval[:TOPICS_PER_SIGNAL],
    ]


async def quran_documents(
    session: AsyncSession, verse_ids: Sequence[int] | None = None
) -> list[RetrievalDocument]:
    """Return the document of every stored verse (or of the given ones), in mushaf order."""
    query = (
        select(QuranVerse.id, QuranVerseSearch.normalized_text, QuranAnnotation)
        .join(QuranVerseSearch, QuranVerseSearch.verse_id == QuranVerse.id)
        .outerjoin(
            QuranAnnotation,
            (QuranAnnotation.surah == QuranVerse.surah) & (QuranAnnotation.ayah == QuranVerse.ayah),
        )
        .order_by(QuranVerse.surah, QuranVerse.ayah)
    )
    if verse_ids is not None:
        query = query.where(QuranVerse.id.in_(verse_ids))
    rows = (await session.execute(query)).all()
    return [
        verse_document(verse_id, folded, annotation_concepts(annotation) if annotation else ())
        for verse_id, folded, annotation in rows
    ]


async def hadith_concepts(
    session: AsyncSession, *, collections: Sequence[str] | None = None
) -> dict[int, tuple[str, ...]]:
    """Return the signal concepts of every hadith (of the given books) a signal record matched."""
    groups: dict[int, list[list[str]]] = defaultdict(list)
    for signal in await session.scalars(select(HadithSignal).order_by(HadithSignal.id)):
        # The link (`hadith_id`) is the first of the matches; every match shares the concepts.
        for match in signal.matches:
            groups[int(match["hadith_id"])].extend(signal_concepts(signal))
    if collections is not None:
        kept = set(
            await session.scalars(
                select(Hadith.id).where(Hadith.id.in_(groups), Hadith.collection.in_(collections))
            )
        )
        groups = {hadith_id: lists for hadith_id, lists in groups.items() if hadith_id in kept}
    return {hadith_id: unique_concepts(lists) for hadith_id, lists in groups.items()}


async def hadith_documents(
    session: AsyncSession,
    *,
    collections: Sequence[str] | None = None,
    hadith_ids: Sequence[int] | None = None,
    concepts: Mapping[int, Sequence[str]] | None = None,
) -> list[RetrievalDocument]:
    """
    Return the document of every stored hadith of the given books (or ids), in store order.

    `concepts` spares reading every signal again when the caller holds them already.
    """
    if concepts is None:
        concepts = await hadith_concepts(session)
    query = select(Hadith.id, Hadith.text).order_by(Hadith.id)
    if collections is not None:
        query = query.where(Hadith.collection.in_(collections))
    if hadith_ids is not None:
        query = query.where(Hadith.id.in_(hadith_ids))
    rows = (await session.execute(query)).all()
    return [
        hadith_document(hadith_id, text, concepts.get(hadith_id, ())) for hadith_id, text in rows
    ]
