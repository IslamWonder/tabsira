"""The constraint vocabulary: every text of the workbook is known, and a new one is not guessed."""

from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError, dataclass

import pytest

from src import messages
from src.services.ontology_constraints import (
    BLOCKING_KINDS,
    KNOWN_CONSTRAINTS,
    ConstraintAction,
    ConstraintKind,
    Forbidden,
    apply_constraint,
    classify_constraint,
)
from src.services.ontology_resolver import OntologyResolver


@pytest.mark.parametrize(("text", "kind"), list(KNOWN_CONSTRAINTS.items()))
def test_each_known_text_has_its_kind(text, kind):
    assert classify_constraint(text) is kind


def test_the_eight_texts_of_the_workbook_cover_every_kind_but_unknown():
    assert len(KNOWN_CONSTRAINTS) == 8
    assert set(KNOWN_CONSTRAINTS.values()) == set(ConstraintKind) - {ConstraintKind.UNKNOWN}


def test_only_the_two_inference_rules_are_hard_blocks():
    assert {
        KNOWN_CONSTRAINTS["لا يُستنتج تشخيص من الصورة"],
        KNOWN_CONSTRAINTS["لا تُستنتج هوية الشخص أو علاقته"],
    } == BLOCKING_KINDS


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_no_constraint_has_no_kind(empty):
    assert classify_constraint(empty) is None


def test_a_spelling_variant_is_the_same_constraint():
    # Without the marks, with another hamza carrier and with extra spaces.
    assert classify_constraint("  لا يستنتج  تشخيص من الصوره ") is ConstraintKind.NO_DIAGNOSIS
    assert classify_constraint("تاكيد الفعل") is ConstraintKind.CONFIRM_ACTION


def test_a_text_the_code_does_not_know_is_unknown_not_guessed():
    # A new rule must be coded before it can be imported: it could be a block.
    assert classify_constraint("لا يُستنتج عمر الشخص من الصورة") is ConstraintKind.UNKNOWN
    # «تأكيد الفعل» is not a prefix match for «تأكيد الفعل التعبدي» or the other way round.
    assert classify_constraint("تأكيد الفعل التعبدي") is ConstraintKind.CONFIRM_WORSHIP_ACTION
    assert classify_constraint("تأكيد") is ConstraintKind.UNKNOWN


# ─── Applying a constraint, on rows of the real workbook ───


@pytest.fixture(scope="module")
def row_of(real_ontology):
    by_id = {row.id: row for row in real_ontology.rows}
    return by_id.__getitem__


def test_an_entity_without_a_constraint_proceeds_and_asks_nothing(row_of):
    rain = row_of("E006")

    outcome = apply_constraint(rain)

    assert outcome == apply_constraint(rain, confirmed=True)
    assert (outcome.action, outcome.kind) == (ConstraintAction.PROCEED, None)
    assert (outcome.question, outcome.rule, outcome.forbids, outcome.before_search) == (
        None,
        None,
        None,
        False,
    )


def test_a_catch_all_asks_for_the_type_or_the_action_before_any_search(row_of):
    plant = row_of("E989")  # «نبات غير محدد»

    outcome = apply_constraint(plant)

    assert outcome.action is ConstraintAction.CLARIFY
    assert outcome.kind is ConstraintKind.SPECIFY_BEFORE_SEARCH
    assert outcome.question == "ما نوع «نبات غير محدد» الذي تقصده، أو ما الذي يحدث هنا بالضبط؟"
    assert outcome.before_search is True
    assert (outcome.rule, outcome.forbids) == (None, None)


def test_the_answer_of_the_person_lifts_a_question(row_of):
    for entity_id in ("E989", "E946", "E217", "E885", "E282", "E298"):
        row = row_of(entity_id)

        asked = apply_constraint(row)
        answered = apply_constraint(row, confirmed=True)

        assert asked.action is ConstraintAction.CLARIFY, entity_id
        assert answered.action is ConstraintAction.PROCEED, entity_id
        assert answered.kind is asked.kind
        assert answered.question is None
        assert answered.before_search is False


@pytest.mark.parametrize(
    ("entity_id", "question"),
    [
        ("E946", messages.QUESTION_CONFIRM_SCENE_MEANING),  # «وحدة مصرح بها»
        ("E217", messages.QUESTION_CONFIRM_ROLE_OR_RELATION),  # «عامل في مهمة»
        ("E885", messages.QUESTION_CONFIRM_ACTION.format(label="مشي رياضي")),
        ("E282", messages.QUESTION_CONFIRM_WORSHIP_ACTION.format(label="شخص يصلي")),
        ("E298", messages.QUESTION_CONFIRM_IDENTITY_OF_THING.format(label="الكعبة")),
    ],
)
def test_each_kind_of_confirmation_asks_its_own_question(row_of, entity_id, question):
    outcome = apply_constraint(row_of(entity_id))

    assert outcome.action is ConstraintAction.CLARIFY
    assert outcome.question == question
    assert outcome.before_search is False
    assert "{" not in outcome.question


def test_an_action_the_scene_shows_needs_no_question_but_a_role_or_a_meaning_always_does(row_of):
    for entity_id in ("E885", "E282"):  # «تأكيد الفعل» and «تأكيد الفعل التعبدي»
        assert apply_constraint(row_of(entity_id), action_observed=True).action is (
            ConstraintAction.PROCEED
        )
    for entity_id in ("E217", "E946", "E298", "E989"):  # role, meaning, identity of a thing, type
        assert apply_constraint(row_of(entity_id), action_observed=True).action is (
            ConstraintAction.CLARIFY
        )


def test_no_diagnosis_is_a_block_that_nothing_lifts(row_of):
    visit = row_of("E171")  # «زيارة شخص مريض», «لا يُستنتج تشخيص من الصورة»
    expected = (ConstraintAction.BLOCK, ConstraintKind.NO_DIAGNOSIS, Forbidden.DIAGNOSIS)

    for options in ({}, {"confirmed": True}, {"action_observed": True}):
        outcome = apply_constraint(visit, **options)

        assert (outcome.action, outcome.kind, outcome.forbids) == expected
        assert outcome.rule == "لا يُستنتج أي تشخيص طبي أو نفسي أو صحي من الصورة."
        assert outcome.question is None


def test_no_identity_is_a_block_that_nothing_lifts(row_of):
    person = row_of("E161")  # «إنسان», «لا تُستنتج هوية الشخص أو علاقته»

    for options in ({}, {"confirmed": True}, {"action_observed": True}):
        outcome = apply_constraint(person, **options)

        assert outcome.action is ConstraintAction.BLOCK
        assert outcome.forbids is Forbidden.PERSON_IDENTITY
        assert outcome.rule == "لا تُستنتج هوية أي شخص ولا علاقته بغيره من الصورة."


def test_every_row_of_the_workbook_gets_an_outcome_and_the_counts_match_the_workbook(real_ontology):
    outcomes = [apply_constraint(row) for row in real_ontology.rows]

    by_action = {action: sum(o.action is action for o in outcomes) for action in ConstraintAction}
    assert by_action == {
        ConstraintAction.PROCEED: 595,  # no constraint
        ConstraintAction.CLARIFY: 123 + 66 + 46 + 32 + 20 + 13,
        ConstraintAction.BLOCK: 68 + 37,
    }
    # A question always names what it asks about, and no template is left unfilled.
    for row, outcome in zip(real_ontology.rows, outcomes, strict=True):
        if outcome.action is ConstraintAction.CLARIFY:
            assert outcome.question and "{" not in outcome.question
        if outcome.action is ConstraintAction.BLOCK:
            assert outcome.rule and outcome.question is None
        if row.is_catch_all:
            assert outcome.before_search is True
    assert sum(o.before_search for o in outcomes) == 13


@dataclass
class Unwritten:
    label_ar: str
    special_constraint: str | None


def test_a_constraint_the_code_does_not_know_asks_a_question_and_is_logged(caplog):
    entity = Unwritten("شيء", "لا يُستنتج عمر الشخص من الصورة")

    with caplog.at_level(logging.WARNING, logger="tabsira.ontology"):
        outcome = apply_constraint(entity)

    assert (outcome.action, outcome.kind) == (ConstraintAction.CLARIFY, ConstraintKind.UNKNOWN)
    assert outcome.question == "وضّح لنا ما تقصده في «شيء» حتى نكمل."
    assert "does not know" in caplog.text
    assert "عمر الشخص" in caplog.text
    # Once the person has answered it does not ask again, and does not log again.
    caplog.clear()
    assert apply_constraint(entity, confirmed=True).action is ConstraintAction.PROCEED
    assert caplog.text == ""


def test_an_outcome_cannot_be_changed(row_of):
    outcome = apply_constraint(row_of("E989"))

    with pytest.raises(FrozenInstanceError):
        outcome.action = ConstraintAction.PROCEED  # type: ignore[misc]


async def test_a_stored_entity_and_a_resolver_candidate_are_constrained_the_same_way(
    db_session, committed_ontology
):
    from src.models import OntologyEntity

    stored = await db_session.get(OntologyEntity, "E161")
    [resolution] = await OntologyResolver(db_session).resolve(["man"])

    assert apply_constraint(stored) == apply_constraint(resolution.best)
    assert apply_constraint(stored).action is ConstraintAction.BLOCK

    [unclear] = await OntologyResolver(db_session).resolve(["xyzzy"])
    assert apply_constraint(unclear.best).before_search is True
