"""
The special constraint of an ontology entity («قيد خاص»), and what it means.

The workbook gives some entities a constraint in plain Arabic. The set of texts is
closed on purpose: each one is enforced by code, so a text this module does not know
is refused at import (see `src.services.ontology_import`) and never guessed at. A
constraint that asks the user something becomes a clarification question; a
constraint that forbids an inference becomes a hard block (`apply_constraint`).
"""

from __future__ import annotations

from enum import StrEnum

from src.arabic import normalize_arabic


class ConstraintKind(StrEnum):
    """What a constraint text requires of the pipeline."""

    # The type or the action is not known: ask before searching for any text.
    SPECIFY_BEFORE_SEARCH = "specify_before_search"
    CONFIRM_SCENE_MEANING = "confirm_scene_meaning"
    CONFIRM_ROLE_OR_RELATION = "confirm_role_or_relation"
    CONFIRM_ACTION = "confirm_action"
    CONFIRM_WORSHIP_ACTION = "confirm_worship_action"
    CONFIRM_IDENTITY_OF_THING = "confirm_identity_of_thing"
    # Hard blocks: the pipeline must never infer these, whatever the user answers.
    NO_DIAGNOSIS = "no_diagnosis"
    NO_PERSON_IDENTITY = "no_person_identity"
    # A text that is in the workbook but not in this table.
    UNKNOWN = "unknown"


# Hard blocks: what is forbidden is an inference, so no answer from the user lifts it.
BLOCKING_KINDS = frozenset({ConstraintKind.NO_DIAGNOSIS, ConstraintKind.NO_PERSON_IDENTITY})

# The texts as the workbook writes them (version 1: eight distinct values).
KNOWN_CONSTRAINTS: dict[str, ConstraintKind] = {
    "تحديد النوع أو الفعل قبل البحث": ConstraintKind.SPECIFY_BEFORE_SEARCH,
    "تأكيد معنى المشهد": ConstraintKind.CONFIRM_SCENE_MEANING,
    "تأكيد الدور أو الصلة": ConstraintKind.CONFIRM_ROLE_OR_RELATION,
    "تأكيد الفعل": ConstraintKind.CONFIRM_ACTION,
    "تأكيد الفعل التعبدي": ConstraintKind.CONFIRM_WORSHIP_ACTION,
    "تأكيد هوية الشيء أو المكان": ConstraintKind.CONFIRM_IDENTITY_OF_THING,
    "لا يُستنتج تشخيص من الصورة": ConstraintKind.NO_DIAGNOSIS,
    "لا تُستنتج هوية الشخص أو علاقته": ConstraintKind.NO_PERSON_IDENTITY,
}

# Compared in search form, so a diacritic or a hamza spelt differently does not make a new constraint.
_BY_SEARCH_FORM = {normalize_arabic(text): kind for text, kind in KNOWN_CONSTRAINTS.items()}


def classify_constraint(text: str | None) -> ConstraintKind | None:
    """Return the kind of a constraint text: None when there is none, UNKNOWN when it is not known."""
    if text is None or not text.strip():
        return None
    return _BY_SEARCH_FORM.get(normalize_arabic(text), ConstraintKind.UNKNOWN)
