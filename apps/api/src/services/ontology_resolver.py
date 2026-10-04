"""
Resolve what a detector or a vision model saw to entities of the world ontology.

`OntologyResolver` takes the labels of a scene (Arabic or English) and the relations
between them, and returns for each label a ranked list of candidate entities, each
with a score and the reason it is a candidate. It never sends the thousand entities
to a model: it asks the database, in this order:

1. **Exact label.** The search form of the label is the search form of an entity's
   label (the article is ignored on either side).
2. **Related object.** The label is one of the objects or synonyms an entity lists
   as related; the earlier in its list, the higher the score.
3. **Similar text.** pg_trgm word similarity between the label and the entity's
   search text, on the trigram index.
4. **Embedding.** A typed hook (`EmbeddingMatcher`) for a later stage; the resolver
   calls one when it is given, and none is implemented yet. An embedding match is a
   suggestion: it never makes a label resolved on its own.

An English label goes through the Arabic hints first (`ontology_hints`), and a label
of several words is also tried one word at a time when the whole did not resolve.

What a candidate is. The ontology proposes concepts; it proves nothing about a scene,
a verse or a hadith. A `RELATED_OBJECT` or `SIMILAR_TEXT` candidate is a neighbour of
the label to explore, not what the photo shows, and the constraint a candidate
carries (`ontology_constraints`) says what must be asked or never inferred before it
is used. The scene's relations only reorder: an action or a concept of a candidate
that the scene brings up (a predicate, or the other thing of a relation) is reported
in `activated` and adds a small bonus. They never create a candidate, and an action
or a concept that no relation brings up stays inactive.

A label that no specific entity resolves gets a catch-all («نبات غير محدد»,
«وثيقة غير محددة», «موقف غير واضح») first, followed by whatever weaker candidates
were found; the catch-all carries the constraint that turns into a clarification
question. At most 10 candidates are returned, and at least 3 whenever the ontology
has that many plausible matches (a similarity below `SIMILAR_FLOOR` is not
plausible). The list is never padded with unrelated entities, and is never empty.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple, Protocol

from sqlalchemy import desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.arabic import contains_arabic, normalize_arabic, search_variants, strip_article, tokens
from src.models.ontology import OntologyEntity
from src.services.ontology_hints import (
    CATCH_ALL_BY_ARABIC_WORD,
    CATCH_ALL_BY_WORD,
    DEFAULT_CATCH_ALL,
    VISION_LABEL_HINTS,
)

MAX_CANDIDATES = 10
# The best candidate must be a specific entity with at least this score for a label to count as resolved.
RESOLVED_MIN_SCORE = 0.7

EXACT_SCORE = 1.0
EXACT_VARIANT_SCORE = 0.95  # the same word with or without its article
RELATED_SCORE = 0.85
RELATED_STEP = 0.02  # lost for each place later in the entity's list
RELATED_FLOOR = 0.71
RELATED_VARIANT_PENALTY = 0.03
SIMILAR_WEIGHT = 0.65  # the best similar text stays below the weakest related object
# Word similarity below this is orthographic noise (a shared prefix), not a likeness.
SIMILAR_FLOOR = 0.6
SIMILAR_LIMIT = 15
EMBEDDING_WEIGHT = 0.6  # below RESOLVED_MIN_SCORE: an embedding never resolves a label alone
WORD_FACTOR = 0.8  # one word of a longer label
SECOND_HINT_FACTOR = 0.9
CONTEXT_STEP = 0.03
CONTEXT_CAP = 0.1
CATCH_ALL_SCORE = 0.3
# A word shorter than this (article removed) is not tried alone.
MIN_WORD_LENGTH = 3

# The Arabic words of the catch-all table, in search form.
_ARABIC_KINDS = {normalize_arabic(word): kind for word, kind in CATCH_ALL_BY_ARABIC_WORD.items()}


class OntologyNotLoadedError(LookupError):
    """The ontology table holds no entity to offer, not even a catch-all."""

    def __init__(self) -> None:
        super().__init__(
            "The ontology has no catch-all entity to offer: import it with `make data` "
            "(python -m src.cli.import_ontology)."
        )


class Reason(StrEnum):
    """Why an entity is a candidate."""

    EXACT_LABEL = "exact_label"
    RELATED_OBJECT = "related_object"
    SIMILAR_TEXT = "similar_text"
    EMBEDDING = "embedding"
    CATCH_ALL = "catch_all"


class Via(StrEnum):
    """What was searched: the label itself, an Arabic hint for it, or one word of it."""

    LABEL = "label"
    HINT = "hint"
    WORD = "word"


@dataclass(frozen=True, slots=True)
class SceneLabel:
    """A thing of the scene: the detector's label, and the vision model's Arabic one if it gave one."""

    text: str
    arabic: str | None = None


@dataclass(frozen=True, slots=True)
class SceneRelation:
    """A relation of the scene between two of its labels, e.g. a person «يقرأ» a book."""

    subject: str
    predicate: str
    object: str


@dataclass(frozen=True, slots=True)
class Candidate:
    """One entity offered for a label, with its score and the reason."""

    entity_id: str
    label_ar: str
    domain: str
    score: float
    reason: Reason
    matched: str  # the text that was searched, in search form
    via: Via
    special_constraint: str | None
    is_catch_all: bool
    # Actions and concepts of the entity that the scene's relations bring up.
    activated: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class LabelResolution:
    """The candidates for one label, best first, and whether a specific entity was found."""

    label: SceneLabel
    candidates: tuple[Candidate, ...]
    # Whether the best candidate is a specific entity (not a catch-all) scoring `RESOLVED_MIN_SCORE`.
    resolved: bool

    @property
    def best(self) -> Candidate:
        return self.candidates[0]


class EmbeddingMatch(NamedTuple):
    """An entity an embedding search found, and how close it is (0 to 1)."""

    entity_id: str
    similarity: float


class EmbeddingMatcher(Protocol):
    """
    The extension point for embedding search; there is no implementation yet.

    Given the text of a label, return the entities whose embeddings are nearest.
    The resolver asks only when the text layers did not resolve the label.
    """

    async def nearest(self, text: str, limit: int) -> Sequence[EmbeddingMatch]:
        """Return up to `limit` entities nearest to `text`."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _Query:
    """An Arabic text to look for, with the forms it can be spelt in; never empty."""

    text: str
    variants: tuple[str, ...]
    via: Via
    factor: float = 1.0

    @property
    def bare(self) -> str:
        """The form without articles: the search text of an entity holds indefinite forms."""
        return min(self.variants, key=len)


def _query(text: str, via: Via, factor: float = 1.0) -> _Query | None:
    variants = search_variants(text)
    return _Query(text, tuple(variants), via, factor) if variants else None


def hint_terms(
    label: str, hints: Mapping[str, tuple[str, ...]] = VISION_LABEL_HINTS
) -> tuple[str, ...]:
    """
    Return the Arabic terms an English label stands for.

    The whole label is tried first, then without a plural ending, then its last word
    the same way («old cell phones» finds «cell phone» through «phone»).
    """
    key = " ".join(label.lower().split())
    last = key.rsplit(" ", 1)[-1]
    for phrase in (key, last):
        for form in (phrase, phrase.removesuffix("es"), phrase.removesuffix("s")):
            if form in hints:
                return hints[form]
    return ()


def _id_number(entity_id: str) -> int:
    return int(entity_id[1:])


def _order(candidate: Candidate) -> tuple[float, int]:
    """Sort key: the highest score first, the lowest id among equals."""
    return -candidate.score, _id_number(candidate.entity_id)


def _stems(*texts: str) -> set[str]:
    return {strip_article(word) for text in texts for word in tokens(text)}


def _context_tokens(label: SceneLabel, relations: Sequence[SceneRelation]) -> frozenset[str]:
    """Return the words of the scene around `label`: its relations' predicates and partners."""
    mine = {normalize_arabic(text) for text in (label.text, label.arabic) if text}
    words: set[str] = set()
    for relation in relations:
        subject, object_ = normalize_arabic(relation.subject), normalize_arabic(relation.object)
        if subject in mine:
            words.update(_stems(relation.predicate, relation.object))
        if object_ in mine:
            words.update(_stems(relation.predicate, relation.subject))
    return frozenset(words)


def _activated(row: OntologyEntity, context: frozenset[str]) -> tuple[str, ...]:
    """Return the actions and concepts of `row` whose every word is a word of the scene's context."""
    if not context:
        return ()
    return tuple(
        term
        for term in (*row.actions_and_uses, *row.contextual_concepts)
        if (stems := _stems(term)) and stems <= context
    )


def _related_score(row: OntologyEntity, variants: Sequence[str]) -> float:
    """Score a related-object match: lower the later the term sits in the entity's list."""
    position = min(index for index, term in enumerate(row.related_norm) if term in variants)
    score = max(RELATED_FLOOR, RELATED_SCORE - RELATED_STEP * position)
    return score if variants[0] in row.related_norm else score - RELATED_VARIANT_PENALTY


def _catch_all_label(label: SceneLabel) -> str:
    """Name the catch-all for a label by the kind of thing its words say it is."""
    texts = [text for text in (label.text, label.arabic) if text]
    for word in reversed([word for text in texts for word in text.lower().split()]):
        if word in CATCH_ALL_BY_WORD:
            return CATCH_ALL_BY_WORD[word]
    for word in reversed([strip_article(word) for text in texts for word in tokens(text)]):
        if word in _ARABIC_KINDS:
            return _ARABIC_KINDS[word]
    return DEFAULT_CATCH_ALL


class OntologyResolver:
    """Resolve scene labels to ontology candidates, on one database session."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        hints: Mapping[str, tuple[str, ...]] = VISION_LABEL_HINTS,
        embedder: EmbeddingMatcher | None = None,
    ) -> None:
        self._session = session
        self._hints = hints
        self._embedder = embedder

    async def resolve(
        self,
        labels: Sequence[SceneLabel | str],
        relations: Sequence[SceneRelation] = (),
    ) -> list[LabelResolution]:
        """
        Resolve every label of a scene; the result is in the order of `labels`.

        Raises `OntologyNotLoadedError` when the ontology table is empty.
        """
        scene = [SceneLabel(label) if isinstance(label, str) else label for label in labels]
        return [await self._resolve_label(label, relations) for label in scene]

    # ─── One label ───

    async def _resolve_label(
        self, label: SceneLabel, relations: Sequence[SceneRelation]
    ) -> LabelResolution:
        context = _context_tokens(label, relations)
        queries = self._queries(label)
        pool: dict[str, Candidate] = {}
        for query in queries:
            self._merge(pool, await self._search(query, context))
        if not self._is_resolved(pool):
            for query in self._word_queries(queries):
                self._merge(pool, await self._search_exact_and_related(query, context))
        if self._embedder is not None and queries and not self._is_resolved(pool):
            self._merge(pool, await self._search_embedding(self._embedder, queries[0], context))

        specific = sorted((c for c in pool.values() if not c.is_catch_all), key=_order)
        if self._is_resolved(pool):
            return LabelResolution(label, tuple(specific[:MAX_CANDIDATES]), resolved=True)
        catch_all = await self._catch_all(label, pool)
        candidates = [catch_all, *specific[: MAX_CANDIDATES - 1]]
        return LabelResolution(label, tuple(candidates), resolved=False)

    def _queries(self, label: SceneLabel) -> list[_Query]:
        """Return the texts to search for a label: its own Arabic, and the hints of an English one."""
        found = [
            _query(text, Via.LABEL)
            for text in (label.arabic, label.text)
            if text and contains_arabic(text)
        ]
        for text in (label.text, label.arabic):
            if text and not contains_arabic(text):
                terms = hint_terms(text, self._hints)
                found.extend(
                    _query(term, Via.HINT, 1.0 if index == 0 else SECOND_HINT_FACTOR)
                    for index, term in enumerate(terms)
                )
        queries: dict[tuple[str, ...], _Query] = {}
        for query in found:
            if query is not None:
                queries.setdefault(query.variants, query)
        return list(queries.values())

    @staticmethod
    def _word_queries(queries: Iterable[_Query]) -> list[_Query]:
        """Return the single words of the multi-word queries, for a label that did not resolve whole."""
        words: dict[str, _Query] = {}
        for query in queries:
            parts = tokens(query.text)
            if len(parts) < 2:
                continue
            for word in parts:
                if len(strip_article(word)) >= MIN_WORD_LENGTH:
                    variants = tuple(search_variants(word))
                    words.setdefault(
                        word, _Query(word, variants, Via.WORD, query.factor * WORD_FACTOR)
                    )
        return list(words.values())

    @staticmethod
    def _is_resolved(pool: Mapping[str, Candidate]) -> bool:
        """Whether the best candidate is a specific entity scoring `RESOLVED_MIN_SCORE`."""
        best = min(pool.values(), key=_order, default=None)
        return best is not None and not best.is_catch_all and best.score >= RESOLVED_MIN_SCORE

    @staticmethod
    def _merge(pool: dict[str, Candidate], found: Iterable[Candidate]) -> None:
        """Keep, for each entity, the candidate with the highest score."""
        for candidate in found:
            known = pool.get(candidate.entity_id)
            if known is None or candidate.score > known.score:
                pool[candidate.entity_id] = candidate

    # ─── The layers ───

    @staticmethod
    def _candidate(
        row: OntologyEntity,
        score: float,
        reason: Reason,
        query: _Query,
        context: frozenset[str],
    ) -> Candidate:
        activated = _activated(row, context)
        bonus = min(CONTEXT_CAP, CONTEXT_STEP * len(activated))
        return Candidate(
            entity_id=row.id,
            label_ar=row.label_ar,
            domain=row.domain,
            score=round(min(1.0, score * query.factor + bonus), 4),
            reason=reason,
            matched=normalize_arabic(query.text),
            via=query.via,
            special_constraint=row.special_constraint,
            is_catch_all=row.is_catch_all,
            activated=activated,
        )

    async def _search(self, query: _Query, context: frozenset[str]) -> list[Candidate]:
        found = await self._search_exact_and_related(query, context)
        return found + await self._search_similar(query, context)

    async def _search_exact_and_related(
        self, query: _Query, context: frozenset[str]
    ) -> list[Candidate]:
        variants = query.variants
        rows = await self._session.scalars(
            select(OntologyEntity).where(
                OntologyEntity.label_norm.in_(variants)
                | OntologyEntity.related_norm.overlap(list(variants))
            )
        )
        found = []
        for row in rows:
            if row.label_norm in variants:
                score = EXACT_SCORE if row.label_norm == variants[0] else EXACT_VARIANT_SCORE
                found.append(self._candidate(row, score, Reason.EXACT_LABEL, query, context))
            else:
                score = _related_score(row, variants)
                found.append(self._candidate(row, score, Reason.RELATED_OBJECT, query, context))
        return found

    async def _search_similar(self, query: _Query, context: frozenset[str]) -> list[Candidate]:
        await self._session.execute(
            select(func.set_config("pg_trgm.word_similarity_threshold", str(SIMILAR_FLOOR), True))
        )
        similarity = func.word_similarity(query.bare, OntologyEntity.search_text)
        rows = await self._session.execute(
            select(OntologyEntity, similarity)
            .where(literal(query.bare).op("<%")(OntologyEntity.search_text))
            .order_by(desc(similarity), OntologyEntity.id)
            .limit(SIMILAR_LIMIT)
        )
        return [
            self._candidate(row, SIMILAR_WEIGHT * score, Reason.SIMILAR_TEXT, query, context)
            for row, score in rows
        ]

    async def _search_embedding(
        self, embedder: EmbeddingMatcher, query: _Query, context: frozenset[str]
    ) -> list[Candidate]:
        matches = await embedder.nearest(query.text, MAX_CANDIDATES)
        similarity = {match.entity_id: match.similarity for match in matches}
        rows = await self._session.scalars(
            select(OntologyEntity).where(OntologyEntity.id.in_(similarity))
        )
        return [
            self._candidate(
                row, EMBEDDING_WEIGHT * similarity[row.id], Reason.EMBEDDING, query, context
            )
            for row in rows
        ]

    # ─── The catch-all ───

    async def _catch_all(self, label: SceneLabel, pool: Mapping[str, Candidate]) -> Candidate:
        """Return the catch-all to offer first for a label nothing resolved."""
        found = min((c for c in pool.values() if c.is_catch_all), key=_order, default=None)
        if found is not None:
            return found
        row = await self._catch_all_entity(label)
        return Candidate(
            entity_id=row.id,
            label_ar=row.label_ar,
            domain=row.domain,
            score=CATCH_ALL_SCORE,
            reason=Reason.CATCH_ALL,
            matched=normalize_arabic(label.arabic or label.text),
            via=Via.LABEL,
            special_constraint=row.special_constraint,
            is_catch_all=True,
        )

    async def _catch_all_entity(self, label: SceneLabel) -> OntologyEntity:
        """Return the catch-all that names the kind of thing the label is, or any catch-all."""
        by_label = await self._session.scalars(
            select(OntologyEntity).where(
                OntologyEntity.is_catch_all.is_(True),
                OntologyEntity.label_norm == normalize_arabic(_catch_all_label(label)),
            )
        )
        if row := by_label.first():
            return row
        # An ontology without that entity: any catch-all, the last one first.
        anything = await self._session.scalars(
            select(OntologyEntity)
            .where(OntologyEntity.is_catch_all.is_(True))
            .order_by(desc(OntologyEntity.id))
        )
        if row := anything.first():
            return row
        raise OntologyNotLoadedError
