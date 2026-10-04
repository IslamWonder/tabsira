"""
The special constraint of an ontology entity («قيد خاص»), and what it means.

The workbook gives some entities a constraint in plain Arabic. The set of texts is
closed on purpose: each one is enforced by code, so a text this module does not know
is refused at import (see `src.services.ontology_import`) and never guessed at. A
constraint that asks the user something becomes a clarification question; a
constraint that forbids an inference becomes a hard block (`apply_constraint`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from src.arabic import normalize_arabic
from src.messages import messages_for

log = logging.getLogger("tabsira.ontology")


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


class ConstraintAction(StrEnum):
    """What the pipeline must do about an entity's constraint."""

    PROCEED = "proceed"  # nothing is asked and nothing is forbidden
    CLARIFY = "clarify"  # ask the question before going on
    BLOCK = "block"  # an inference is forbidden, whatever anyone answers


class Forbidden(StrEnum):
    """The inference a hard block forbids; a validator can reject output that makes it."""

    DIAGNOSIS = "diagnosis"
    PERSON_IDENTITY = "person_identity"


class ConstrainedEntity(Protocol):
    """What `apply_constraint` reads: an ontology row, an entity or a resolver candidate."""

    @property
    def label_ar(self) -> str:
        raise NotImplementedError

    @property
    def special_constraint(self) -> str | None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ConstraintOutcome:
    """
    The result of applying a constraint.

    `question` is set for `CLARIFY`: Arabic text to put to the person. `rule` and
    `forbids` are set for `BLOCK`: the Arabic statement of the rule, for the prompts
    and the screen, and the inference it forbids. `before_search` is true when the
    constraint says no verse or hadith may be looked up until the question is answered.
    """

    action: ConstraintAction
    kind: ConstraintKind | None
    question: str | None = None
    rule: str | None = None
    forbids: Forbidden | None = None
    before_search: bool = False


# The language of the questions is the default one until a language reaches the pipeline.
_TEXT = messages_for()
_QUESTIONS = {
    ConstraintKind.SPECIFY_BEFORE_SEARCH: _TEXT.question_specify_before_search,
    ConstraintKind.CONFIRM_SCENE_MEANING: _TEXT.question_confirm_scene_meaning,
    ConstraintKind.CONFIRM_ROLE_OR_RELATION: _TEXT.question_confirm_role_or_relation,
    ConstraintKind.CONFIRM_ACTION: _TEXT.question_confirm_action,
    ConstraintKind.CONFIRM_WORSHIP_ACTION: _TEXT.question_confirm_worship_action,
    ConstraintKind.CONFIRM_IDENTITY_OF_THING: _TEXT.question_confirm_identity_of_thing,
    ConstraintKind.UNKNOWN: _TEXT.question_unknown_constraint,
}
_RULES = {
    ConstraintKind.NO_DIAGNOSIS: (Forbidden.DIAGNOSIS, _TEXT.rule_no_diagnosis),
    ConstraintKind.NO_PERSON_IDENTITY: (
        Forbidden.PERSON_IDENTITY,
        _TEXT.rule_no_person_identity,
    ),
}
# An action the scene already shows needs no question; a role or a meaning never shows.
_ASKED_ONLY_WHEN_ACTION_IS_NOT_SEEN = frozenset(
    {ConstraintKind.CONFIRM_ACTION, ConstraintKind.CONFIRM_WORSHIP_ACTION}
)


def apply_constraint(
    entity: ConstrainedEntity, *, confirmed: bool = False, action_observed: bool = False
) -> ConstraintOutcome:
    """
    Turn the special constraint of `entity` into what the pipeline must do.

    No constraint: proceed. A constraint that asks (specify the type or the action,
    confirm the meaning, the role, the action, the identity of a thing): proceed when
    the person already answered (`confirmed`), or, for an action, when the scene
    shows it (`action_observed`); otherwise a clarification question. A constraint
    that forbids an inference (no diagnosis, no identity of a person or relation):
    always a block, because no answer makes the inference allowed. A constraint text
    the code does not know is a question too, never silently ignored.
    """
    kind = classify_constraint(entity.special_constraint)
    if kind is None:
        return ConstraintOutcome(ConstraintAction.PROCEED, None)
    if kind in BLOCKING_KINDS:
        forbids, rule = _RULES[kind]
        return ConstraintOutcome(ConstraintAction.BLOCK, kind, rule=rule, forbids=forbids)
    if confirmed or (action_observed and kind in _ASKED_ONLY_WHEN_ACTION_IS_NOT_SEEN):
        return ConstraintOutcome(ConstraintAction.PROCEED, kind)
    if kind is ConstraintKind.UNKNOWN:
        log.warning(
            "The ontology holds a constraint this code does not know: %r", entity.special_constraint
        )
    return ConstraintOutcome(
        ConstraintAction.CLARIFY,
        kind,
        question=_QUESTIONS[kind].format(label=entity.label_ar),
        before_search=kind is ConstraintKind.SPECIFY_BEFORE_SEARCH,
    )
