from __future__ import annotations

import pytest

from vision.vocabulary import (
    ARABIC_LABELS,
    COCO_CLASSES,
    DEFAULT_VOCABULARY,
    arabic_label,
    normalise_vocabulary,
)


def test_default_vocabulary_has_no_duplicates() -> None:
    assert len(DEFAULT_VOCABULARY) == 114
    assert len(set(DEFAULT_VOCABULARY)) == len(DEFAULT_VOCABULARY)


def test_coco_has_its_80_classes() -> None:
    assert len(COCO_CLASSES) == 80
    assert len(set(COCO_CLASSES)) == 80


def test_every_label_has_an_arabic_one_and_none_is_unused() -> None:
    known = set(DEFAULT_VOCABULARY) | set(COCO_CLASSES)

    assert known - set(ARABIC_LABELS) == set()
    assert set(ARABIC_LABELS) - known == set()


def test_arabic_labels_are_arabic() -> None:
    for label, arabic in ARABIC_LABELS.items():
        assert arabic.strip() == arabic, label
        assert all("؀" <= char <= "ۿ" or char == " " for char in arabic), label


def test_arabic_label_is_none_for_an_unknown_label() -> None:
    assert arabic_label("olive") == "زيتون"
    assert arabic_label("sextant") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Cup, PLATE ,  water   bottle", ["cup", "plate", "water bottle"]),
        ("cup,cup, Cup", ["cup"]),
        (["Cup", "plate, bowl"], ["cup", "plate", "bowl"]),
        (("tree",), ["tree"]),
    ],
)
def test_normalise_vocabulary(raw: object, expected: list[str]) -> None:
    assert normalise_vocabulary(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", [None, "", " , ,", [], ["", " "]])
def test_nothing_usable_gives_the_default_vocabulary(raw: object) -> None:
    labels = normalise_vocabulary(raw)  # type: ignore[arg-type]

    assert labels == list(DEFAULT_VOCABULARY)
