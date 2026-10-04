"""
Gold scenes: what a correct scene analysis must and must not contain.

A gold file (tests/evaluation/scenes/gold.json) lists each image with the
entities a description must name, the actions it should report, the claims it
must never make, and whether the scene is sensitive. Patterns are compared on
the normalised text (see `leak_guard.normalize_arabic`), word by word: a
pattern matches a word that starts with it, after an optional clitic, so
«القطة» matches «قطه» and "cats" matches "cat". A pattern of one or two letters
(«يد», «تل», "tv") must match a whole word, or «تل» would match «تلفاز».
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from src.pipeline.leak_guard import normalize_arabic
from src.pipeline.schemas import SensitiveCategory

SHORT_PATTERN = 2
# Arabic clitics that may precede a word: conjunctions, prepositions, the article.
CLITICS = ("وبال", "وال", "بال", "فال", "كال", "لل", "ال", "و", "ف", "ب", "ل", "ك")

type Group = list[str]


class _Gold(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ForbiddenClaim(_Gold):
    """A claim no scene may make, with the reason it is wrong."""

    claim: str
    patterns: Group


class GoldRules(_Gold):
    """Rules that hold for every scene."""

    forbidden_actions: list[ForbiddenClaim]
    # Words that state a person's gender, age or religion (v2 §0, rule 6).
    identity_terms: list[str]


class Provenance(_Gold):
    origin: str
    source: str
    generator: str
    prompt: str | None


class GoldScene(_Gold):
    """One image and its expectations. A group is satisfied by any of its patterns."""

    id: str
    image: str
    sha256: str
    provenance: Provenance
    kind: str
    notes: str
    required_entities: list[Group]
    expected_actions: list[Group]
    forbidden_actions: list[Group]
    # Acceptable only as an inference: reported as observed, it is a forbidden claim.
    inferred_only_actions: list[Group]
    # Things the image does not contain; naming one as an entity is a hallucination.
    forbidden_entities: list[Group]
    sensitive: bool
    expected_categories: list[SensitiveCategory] = []
    expects_clarification: bool | None


class GoldSet(_Gold):
    version: int
    description: str
    provenance_note: str
    rules: GoldRules
    scenes: list[GoldScene]


def load_gold(path: Path) -> GoldSet:
    """Read and validate a gold file."""
    return GoldSet.model_validate_json(path.read_text(encoding="utf-8"))


def _words(text: str) -> list[str]:
    return normalize_arabic(text).split()


def _stems(word: str) -> list[str]:
    """Return the word, and the word without each clitic it may start with."""
    return [word] + [word[len(clitic) :] for clitic in CLITICS if word.startswith(clitic)]


def _word_matches(word: str, pattern: str, *, exact: bool) -> bool:
    exact = exact or len(pattern) <= SHORT_PATTERN
    return any(
        stem == pattern if exact else stem.startswith(pattern) for stem in _stems(word) if stem
    )


def matches(pattern: str, text: str, *, exact: bool = False) -> bool:
    """Return whether `pattern` (one or more words) occurs in `text`."""
    wanted = _words(pattern)
    words = _words(text)
    if not wanted:
        return False
    for start in range(len(words) - len(wanted) + 1):
        window = words[start : start + len(wanted)]
        if all(_word_matches(w, p, exact=exact) for w, p in zip(window, wanted, strict=True)):
            return True
    return False


def first_match(group: Group, texts: list[str], *, exact: bool = False) -> str | None:
    """Return the first pattern of `group` found in any of `texts`, or None."""
    for pattern in group:
        if any(matches(pattern, text, exact=exact) for text in texts):
            return pattern
    return None
