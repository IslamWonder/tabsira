"""The ontology tables as the models build them: columns, constraints and the indexes search needs."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from src.models import Base, CandidateKind, CandidateStatus, OntologyCandidate, OntologyEntity

SHA = "0" * 64


def entity(entity_id: str = "E001", **columns) -> OntologyEntity:
    values = {
        "id": entity_id,
        "label_ar": "سماء",
        "related_objects": ["سماء", "أفق"],
        "actions_and_uses": ["نظر"],
        "contextual_concepts": ["خلق"],
        "domain": "السماء والطقس",
        "raw": {"row": 6},
        "label_norm": "سماء",
        "related_norm": ["سماء", "افق"],
        "search_text": "سماء افق",
        "source_sha256": SHA,
    }
    return OntologyEntity(**{**values, **columns})


def test_both_tables_live_in_the_app_schema():
    assert {"app.ontology_entities", "app.ontology_candidates"} <= set(Base.metadata.tables)


def test_the_entity_table_declares_a_trigram_index_on_the_search_column():
    indexes = {index.name: index for index in OntologyEntity.__table__.indexes}

    assert "USING gin (search_text gin_trgm_ops)" in str(
        CreateIndex(indexes["ix_ontology_entities_search_text_trgm"]).compile(
            dialect=postgresql.dialect()
        )
    )
    assert {"ix_ontology_entities_label_norm", "ix_ontology_entities_related_norm"} <= set(indexes)


async def test_an_entity_keeps_its_arrays_and_its_raw_cells(db_session):
    db_session.add(entity(raw={"row": 6, "label_ar": "سماء", "special_constraint": None}))
    await db_session.flush()

    stored = await db_session.scalar(select(OntologyEntity))

    assert stored.related_objects == ["سماء", "أفق"]
    assert stored.raw == {"row": 6, "label_ar": "سماء", "special_constraint": None}
    assert stored.special_constraint is None
    assert stored.is_catch_all is False
    assert stored.imported_at is not None


@pytest.mark.parametrize("bad_id", ["X001", "E01", "e001", "E00A", "001"])
async def test_an_entity_id_must_be_a_capital_e_and_digits(db_session, bad_id):
    db_session.add(entity(bad_id))

    with pytest.raises(IntegrityError, match="id_format"):
        await db_session.flush()


async def test_an_entity_id_is_unique(db_session):
    db_session.add_all([entity("E001"), entity("E001", label_ar="شمس")])

    with pytest.raises(IntegrityError, match="pk_ontology_entities"):
        await db_session.flush()


async def test_the_search_column_is_found_by_trigram_similarity_and_the_array_by_containment(
    db_session,
):
    db_session.add_all(
        [
            entity("E001", search_text="سماء افق شمس"),
            entity(
                "E002", label_ar="ماء", label_norm="ماء", related_norm=["ماء"], search_text="ماء"
            ),
        ]
    )
    await db_session.flush()

    similar = await db_session.scalars(
        select(OntologyEntity.id).where(
            func.word_similarity("سماء", OntologyEntity.search_text) > 0.9
        )
    )
    related = await db_session.scalars(
        select(OntologyEntity.id).where(OntologyEntity.related_norm.contains(["افق"]))
    )

    assert list(similar) == ["E001"]
    assert list(related) == ["E001"]


async def test_the_trigram_operator_can_use_the_index(db_session):
    db_session.add(entity("E001"))
    await db_session.flush()
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))

    plan = "\n".join(
        (
            await db_session.execute(
                text("EXPLAIN SELECT id FROM app.ontology_entities WHERE 'سماء' <% search_text")
            )
        ).scalars()
    )

    assert "ix_ontology_entities_search_text_trgm" in plan


async def test_a_candidate_starts_new_with_one_sighting(db_session):
    db_session.add(OntologyCandidate(kind="label", term="طائرة مسيرة", term_norm="طايره مسيره"))
    await db_session.flush()

    stored = await db_session.scalar(select(OntologyCandidate))

    assert stored.id >= 1
    assert (stored.count, stored.status, stored.examples, stored.sources) == (1, "new", [], [])
    assert stored.entity_id is None
    assert stored.first_seen_at <= stored.last_seen_at


async def test_a_candidate_is_one_row_per_kind_and_normalised_term(db_session):
    db_session.add_all(
        [
            OntologyCandidate(kind="label", term="طائرة", term_norm="طايره"),
            OntologyCandidate(kind="concept", term="طائرة", term_norm="طايره"),
        ]
    )
    await db_session.flush()
    db_session.add(OntologyCandidate(kind="label", term="طَائِرَة", term_norm="طايره"))

    with pytest.raises(IntegrityError, match="uq_ontology_candidates_kind_term_norm"):
        await db_session.flush()


@pytest.mark.parametrize(
    ("columns", "constraint"),
    [
        ({"kind": "thing"}, "ck_ontology_candidates_kind"),
        ({"status": "pending"}, "ck_ontology_candidates_status"),
        ({"count": 0}, "ck_ontology_candidates_count_positive"),
    ],
)
async def test_a_candidate_refuses_values_outside_its_vocabulary(db_session, columns, constraint):
    db_session.add(OntologyCandidate(**{"kind": "label", "term": "x", "term_norm": "x", **columns}))

    with pytest.raises(IntegrityError, match=constraint):
        await db_session.flush()


async def test_deleting_an_entity_keeps_the_candidate_that_was_folded_into_it(db_session):
    db_session.add(entity("E001"))
    await db_session.flush()
    db_session.add(
        OntologyCandidate(
            kind="label", term="جوال", term_norm="جوال", entity_id="E001", status="accepted"
        )
    )
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.ontology_entities WHERE id = 'E001'"))
    db_session.expire_all()
    stored = await db_session.scalar(select(OntologyCandidate))

    assert (stored.entity_id, stored.status) == (None, "accepted")


def test_the_vocabularies_are_the_ones_the_constraints_allow():
    assert {member.value for member in CandidateKind} == {"label", "concept"}
    assert {member.value for member in CandidateStatus} == {"new", "accepted", "rejected"}
