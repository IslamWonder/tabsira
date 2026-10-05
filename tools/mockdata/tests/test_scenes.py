from __future__ import annotations

import pytest

from mockdata.scenes import describe


@pytest.mark.parametrize(
    ("name", "category", "labels", "line"),
    [
        ("camels.jpg", "animal", ["camel"], "جمل"),
        ("white-cat-garden.jpg", "cat", ["cat", "garden"], "قطة في الحديقة"),
        ("cat-and-dog-park.jpg", "cat", ["cat", "dog", "park"], "قطة وكلب في المتنزه"),
        ("market-red.jpg", "city", ["market"], "منظر من السوق"),
        ("strawberries-tomatoes.jpg", "food", ["strawberry", "tomato"], "فراولة وطماطم"),
        ("cat-kitten.jpg", "cat", ["cat"], "قطة"),
        ("zzz-unknown.jpg", "nature", ["nature"], "منظر من الطبيعة"),
        ("zzz.jpg", "", [], "منظر"),
    ],
)
def test_scene(name: str, category: str, labels: list[str], line: str) -> None:
    scene = describe(name, category)
    assert scene.labels == labels
    assert scene.ar == line


def test_unknown_words_are_dropped_and_at_most_two_subjects_kept() -> None:
    scene = describe("cat-dog-horse-qwerty.jpg", "animal")
    assert scene.labels == ["cat", "dog"]
    assert "qwerty" not in scene.ar
