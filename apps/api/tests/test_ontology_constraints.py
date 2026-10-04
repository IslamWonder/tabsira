"""The constraint vocabulary: every text of the workbook is known, and a new one is not guessed."""

from __future__ import annotations

import pytest

from src.services.ontology_constraints import (
    BLOCKING_KINDS,
    KNOWN_CONSTRAINTS,
    ConstraintKind,
    classify_constraint,
)


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
