"""
Remember what a model proposed that the ontology does not know.

The ontology workbook is never edited by the application. Every label that the
resolver could not place, and every concept a planner proposed that no entity
holds, is recorded in `app.ontology_candidates` with how many times it came up and
a few examples. A person reviews the table and merges the accepted terms into a new
version of the workbook (master prompt v2, section 7).

An example is a short piece of model-written context, for instance the scene
description a label came from. It is never the person's own text, and a caller must
not pass one from a scene that is not kept (a sensitive scene is neither shown nor
stored). No user, session or photo is recorded here, only the term and its context.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import ARRAY, ColumnElement, Text, any_, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.arabic import bare_form
from src.models.ontology import CandidateKind, OntologyCandidate, OntologyEntity
from src.services.ontology_resolver import LabelResolution, Reason

MAX_EXAMPLES = 5
MAX_EXAMPLE_LENGTH = 200
MAX_TERM_LENGTH = 200

# Who proposed a term: the stage of the pipeline.
SOURCE_DETECTOR = "detector"
SOURCE_VISION_MODEL = "vision_model"
SOURCE_PLANNER = "planner"

_UNIQUE_TERM = "uq_ontology_candidates_kind_term_norm"


def _clip(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


async def record_candidate(
    session: AsyncSession,
    term: str,
    kind: CandidateKind,
    *,
    source: str,
    example: str | None = None,
) -> OntologyCandidate | None:
    """
    Record one sighting of `term` and return its row; None when the term has no letters.

    The first sighting creates the row, keeping the spelling as it came; each later
    one, in any spelling that has the same search form, adds one to `count`, adds the
    `source` if it is new, and adds the `example` while there are fewer than
    `MAX_EXAMPLES` and it is not there yet. A row that was already reviewed keeps its
    status. The caller owns the transaction.
    """
    term = _clip(term, MAX_TERM_LENGTH)
    # The article is not part of the term: «طائرة» and «الطائرة» are one candidate.
    term_norm = bare_form(term)
    if not term_norm:
        return None
    sample = _clip(example, MAX_EXAMPLE_LENGTH) if example else None

    insertion = insert(OntologyCandidate).values(
        kind=kind.value,
        term=term,
        term_norm=term_norm,
        sources=[source],
        examples=[sample] if sample else [],
    )
    sources: ColumnElement[list[str]] = case(
        (literal(source) == any_(OntologyCandidate.sources), OntologyCandidate.sources),
        else_=func.array_append(OntologyCandidate.sources, source, type_=ARRAY(Text)),
    )
    examples: ColumnElement[list[str]] | Any = OntologyCandidate.examples
    if sample:
        examples = case(
            (
                or_(
                    literal(sample) == any_(OntologyCandidate.examples),
                    func.cardinality(OntologyCandidate.examples) >= MAX_EXAMPLES,
                ),
                OntologyCandidate.examples,
            ),
            else_=func.array_append(OntologyCandidate.examples, sample, type_=ARRAY(Text)),
        )
    upsert = insertion.on_conflict_do_update(
        constraint=_UNIQUE_TERM,
        set_={
            "count": OntologyCandidate.count + 1,
            "last_seen_at": func.now(),
            "sources": sources,
            "examples": examples,
        },
    ).returning(OntologyCandidate)
    return await session.scalar(upsert, execution_options={"populate_existing": True})


async def record_unresolved(
    session: AsyncSession,
    resolutions: Iterable[LabelResolution],
    *,
    source: str,
    example: str | None = None,
) -> list[OntologyCandidate]:
    """
    Record the labels of a scene that no entity resolved.

    A label counts when the best the resolver could offer was a catch-all it chose
    for lack of anything better. A label that matched a catch-all entity exactly (a
    detector that says «document») is known to the ontology and is not recorded. The
    vision model's Arabic label is recorded in preference to the detector's English.
    """
    recorded = []
    for resolution in resolutions:
        if resolution.resolved or resolution.best.reason is not Reason.CATCH_ALL:
            continue
        label = resolution.label
        candidate = await record_candidate(
            session, label.arabic or label.text, CandidateKind.LABEL, source=source, example=example
        )
        if candidate is not None:
            recorded.append(candidate)
    return recorded


async def known_concept_forms(session: AsyncSession) -> frozenset[str]:
    """Return the bare form (no article) of every label, related object, action and concept."""
    rows = await session.execute(
        select(
            OntologyEntity.label_ar,
            OntologyEntity.related_objects,
            OntologyEntity.actions_and_uses,
            OntologyEntity.contextual_concepts,
        )
    )
    forms: set[str] = set()
    for label, *lists in rows:
        for text in (label, *(item for items in lists for item in items)):
            forms.add(bare_form(text))
    return frozenset(forms - {""})


async def record_unknown_concepts(
    session: AsyncSession,
    concepts: Sequence[str],
    *,
    source: str = SOURCE_PLANNER,
    example: str | None = None,
) -> list[OntologyCandidate]:
    """
    Record the concepts a model proposed that no entity of the ontology holds.

    A concept is known when its bare form (search form, no article) is the one of a
    label, a related object, an action or a concept of any entity; the others are
    recorded as candidates of kind `concept`.
    """
    known = await known_concept_forms(session)
    recorded = []
    for concept in concepts:
        if bare_form(concept) in known:
            continue
        candidate = await record_candidate(
            session, concept, CandidateKind.CONCEPT, source=source, example=example
        )
        if candidate is not None:
            recorded.append(candidate)
    return recorded
