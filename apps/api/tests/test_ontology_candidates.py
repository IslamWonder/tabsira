"""Recording what the ontology did not know, for a person to review into a new version of the workbook."""

from __future__ import annotations

from hashlib import sha256

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.arabic import bare_form
from src.models import CandidateKind, CandidateStatus, OntologyCandidate
from src.services.ontology_candidates import (
    MAX_EXAMPLE_LENGTH,
    MAX_EXAMPLES,
    MAX_TERM_LENGTH,
    SOURCE_DETECTOR,
    SOURCE_PLANNER,
    SOURCE_VISION_MODEL,
    known_concept_forms,
    record_candidate,
    record_unknown_concepts,
    record_unresolved,
)
from src.services.ontology_resolver import OntologyResolver, SceneLabel
from tests.support_ontology import REAL_WORKBOOK

LABEL = CandidateKind.LABEL


async def rows(session) -> list[OntologyCandidate]:
    return list(
        (await session.scalars(select(OntologyCandidate).order_by(OntologyCandidate.id))).all()
    )


# ─── One term ───


async def test_a_first_sighting_creates_the_row_with_its_context(db_session):
    row = await record_candidate(
        db_session, "طائرة مسيرة", LABEL, source=SOURCE_VISION_MODEL, example="طائرة صغيرة فوق حقل"
    )

    assert (row.kind, row.term, row.term_norm) == ("label", "طائرة مسيرة", "طايره مسيره")
    assert (row.count, row.status) == (1, CandidateStatus.NEW.value)
    assert row.sources == ["vision_model"]
    assert row.examples == ["طائرة صغيرة فوق حقل"]
    assert (row.entity_id, row.reviewed_at, row.review_note) == (None, None, None)
    assert row.first_seen_at == row.last_seen_at


async def test_each_new_sighting_adds_one_to_the_count_whatever_its_spelling(db_session):
    first = await record_candidate(db_session, "طائرة", LABEL, source=SOURCE_DETECTOR)
    second = await record_candidate(db_session, "الطَّائِرَة", LABEL, source=SOURCE_DETECTOR)
    third = await record_candidate(db_session, "  طائرة ", LABEL, source=SOURCE_DETECTOR)

    assert first.id == second.id == third.id
    assert (await rows(db_session))[0].count == 3
    # The spelling of the first sighting is the one kept; the clock moved on.
    assert third.term == "طائرة"
    assert third.last_seen_at >= third.first_seen_at


async def test_an_english_label_is_recorded_in_lower_case_form(db_session):
    first = await record_candidate(db_session, "Drone", LABEL, source=SOURCE_DETECTOR)
    second = await record_candidate(db_session, "drone ", LABEL, source=SOURCE_DETECTOR)

    assert (first.term, first.term_norm, second.count) == ("Drone", "drone", 2)


async def test_a_label_and_a_concept_with_the_same_text_are_two_rows(db_session):
    await record_candidate(db_session, "تواضع", CandidateKind.LABEL, source=SOURCE_DETECTOR)
    await record_candidate(db_session, "تواضع", CandidateKind.CONCEPT, source=SOURCE_PLANNER)

    assert [(r.kind, r.count) for r in await rows(db_session)] == [("label", 1), ("concept", 1)]


async def test_sources_are_listed_once_each_in_the_order_they_came(db_session):
    for source in (SOURCE_DETECTOR, SOURCE_VISION_MODEL, SOURCE_DETECTOR, SOURCE_VISION_MODEL):
        row = await record_candidate(db_session, "منطاد", LABEL, source=source)

    assert row.sources == ["detector", "vision_model"]
    assert row.count == 4


async def test_examples_are_kept_up_to_a_limit_without_repeats(db_session):
    for number in range(MAX_EXAMPLES + 3):
        row = await record_candidate(
            db_session, "منطاد", LABEL, source=SOURCE_VISION_MODEL, example=f"مشهد {number}"
        )
    again = await record_candidate(
        db_session, "منطاد", LABEL, source=SOURCE_VISION_MODEL, example="مشهد 0"
    )
    without = await record_candidate(db_session, "منطاد", LABEL, source=SOURCE_VISION_MODEL)

    assert row.examples == [f"مشهد {number}" for number in range(MAX_EXAMPLES)]
    assert again.examples == without.examples == row.examples
    assert without.count == MAX_EXAMPLES + 5


async def test_an_example_that_repeats_one_already_kept_is_not_added_again(db_session):
    await record_candidate(db_session, "منطاد", LABEL, source=SOURCE_PLANNER, example="سماء صافية")
    row = await record_candidate(
        db_session, "منطاد", LABEL, source=SOURCE_PLANNER, example="سماء  صافية"
    )

    assert row.examples == ["سماء صافية"]


async def test_a_long_term_and_a_long_example_are_cut(db_session):
    row = await record_candidate(
        db_session, "ك" * 500, LABEL, source=SOURCE_PLANNER, example="م\n" * 500
    )

    assert len(row.term) == MAX_TERM_LENGTH
    assert len(row.examples[0]) == MAX_EXAMPLE_LENGTH
    assert "\n" not in row.examples[0]


@pytest.mark.parametrize("empty", ["", "   ", "،؛.", "\N{ARABIC TATWEEL}"])
async def test_a_term_without_a_letter_is_not_recorded(db_session, empty):
    assert await record_candidate(db_session, empty, LABEL, source=SOURCE_DETECTOR) is None
    assert await rows(db_session) == []


async def test_a_reviewed_candidate_keeps_its_status_and_note_but_still_counts(db_session):
    row = await record_candidate(db_session, "منطاد", LABEL, source=SOURCE_DETECTOR)
    row.status = CandidateStatus.ACCEPTED.value
    row.review_note = "تُضاف في الإصدار التالي"
    await db_session.flush()

    again = await record_candidate(db_session, "منطاد", LABEL, source=SOURCE_DETECTOR)

    assert (again.status, again.review_note, again.count) == (
        "accepted",
        "تُضاف في الإصدار التالي",
        2,
    )


async def test_the_returned_row_is_the_stored_one_not_a_stale_copy(db_session):
    await record_candidate(db_session, "منطاد", LABEL, source=SOURCE_DETECTOR)
    stored = (await rows(db_session))[0]

    await record_candidate(db_session, "منطاد", LABEL, source=SOURCE_DETECTOR)

    assert stored.count == 2


# ─── The labels of a scene ───


async def test_only_labels_nothing_resolved_are_recorded_with_their_context(
    db_session, committed_ontology
):
    labels = ["هاتف", "document", "xyzzy", "bush", "نبتة", SceneLabel("dinosaur", "ديناصور")]
    resolutions = await OntologyResolver(db_session).resolve(labels)

    recorded = await record_unresolved(
        db_session, resolutions, source=SOURCE_DETECTOR, example="حقل في الصباح"
    )

    # «هاتف» resolved; «document» matched the catch-all «وثيقة غير محددة» exactly, which is known.
    assert [r.term for r in recorded] == ["xyzzy", "bush", "نبتة", "ديناصور"]
    assert all(r.kind == "label" and r.count == 1 for r in recorded)
    assert all(r.examples == ["حقل في الصباح"] and r.sources == ["detector"] for r in recorded)

    again = await record_unresolved(db_session, resolutions, source=SOURCE_VISION_MODEL)

    assert [r.count for r in again] == [2, 2, 2, 2]
    assert again[0].sources == ["detector", "vision_model"]
    assert len(await rows(db_session)) == 4


async def test_a_scene_that_resolves_completely_records_nothing(db_session, committed_ontology):
    resolutions = await OntologyResolver(db_session).resolve(["هاتف", "cell phone", "كتاب"])

    assert await record_unresolved(db_session, resolutions, source=SOURCE_DETECTOR) == []
    assert await rows(db_session) == []


async def test_a_label_without_letters_in_an_unresolved_scene_is_skipped(
    db_session, committed_ontology
):
    resolutions = await OntologyResolver(db_session).resolve(["", "،"])

    assert all(not r.resolved for r in resolutions)
    assert await record_unresolved(db_session, resolutions, source=SOURCE_DETECTOR) == []


# ─── The concepts a planner proposed ───


async def test_the_forms_the_ontology_knows_include_labels_actions_and_concepts(
    db_session, committed_ontology
):
    known = await known_concept_forms(db_session)

    assert {"سماء", "نظر", "شكر", "افق", bare_form("تعاقب الليل والنهار")} <= known
    assert "" not in known
    assert "ديناصور" not in known


async def test_only_concepts_the_ontology_does_not_hold_are_recorded(
    db_session, committed_ontology
):
    recorded = await record_unknown_concepts(
        db_session,
        ["الشُّكر", "إحياء الأرض", "تواضع الغني", "شكر", "،"],
        example="غني يتصدق في الخفاء",
    )

    assert [(r.term, r.kind, r.sources, r.examples) for r in recorded] == [
        ("تواضع الغني", "concept", ["planner"], ["غني يتصدق في الخفاء"])
    ]

    again = await record_unknown_concepts(db_session, ["تواضع الغني"], source=SOURCE_VISION_MODEL)

    assert (again[0].count, again[0].sources) == (2, ["planner", "vision_model"])


async def test_the_workbook_is_never_modified_by_any_of_this(db_session, committed_ontology):
    before = sha256(REAL_WORKBOOK.read_bytes()).hexdigest()
    resolutions = await OntologyResolver(db_session).resolve(["xyzzy"])

    await record_unresolved(db_session, resolutions, source=SOURCE_DETECTOR)
    await record_unknown_concepts(db_session, ["تواضع الغني"])

    assert (
        sha256(REAL_WORKBOOK.read_bytes()).hexdigest() == before == committed_ontology.source_sha256
    )


async def test_a_kind_outside_the_vocabulary_is_refused_by_the_database(db_session):
    db_session.add(OntologyCandidate(kind="phrase", term="x", term_norm="x"))

    with pytest.raises(IntegrityError, match="ck_ontology_candidates_kind"):
        await db_session.flush()
