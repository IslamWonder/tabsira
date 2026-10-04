from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.evaluation.gold import first_match, load_gold, matches

SCENES = Path(__file__).parent / "evaluation" / "scenes"


def test_the_gold_set_is_complete_and_every_image_is_the_one_annotated():
    gold = load_gold(SCENES / "gold.json")

    ids = [scene.id for scene in gold.scenes]
    assert len(ids) == len(set(ids)) == 15
    assert sum(scene.sensitive for scene in gold.scenes) == 1
    for scene in gold.scenes:
        image = SCENES / scene.image
        assert hashlib.sha256(image.read_bytes()).hexdigest() == scene.sha256, scene.id
        assert scene.required_entities, scene.id
        assert all(group for group in scene.required_entities), scene.id
        assert scene.provenance.origin in {"generated", "most likely generated"}
    # Every image of the folder is in the gold set: nothing is benchmarked unannotated.
    assert {path.name for path in SCENES.glob("*.jpg")} == {s.image for s in gold.scenes}


@pytest.mark.parametrize(
    ("pattern", "text"),
    [
        ("قطه", "تقف القطة بجانب الوعاء"),
        ("قطه", "وبالقطة"),
        ("cat", "Two cats on a mat"),
        ("درب التبانه", "يظهر درب التبانة فوق الكثبان"),
        ("يقرا", "شخص يقرأ"),
        ("يد", "تمسك يد الهاتف"),
        ("tv", "a TV"),
    ],
)
def test_a_pattern_matches_the_start_of_a_word_after_a_clitic(pattern, text):
    assert matches(pattern, text)


@pytest.mark.parametrize(
    ("pattern", "text", "exact"),
    [
        ("تل", "تلفاز في الغرفة", False),
        ("يد", "يدخل الضوء", False),
        ("قطه", "قطرات المطر", False),
        ("رجال", "الأرجل الأربع", True),
        ("طفل", "طفلة صغيرة", True),
        ("درب التبانه", "درب طويل", False),
        ("", "أي نص", False),
        ("مطر", "", False),
    ],
)
def test_a_pattern_does_not_match_inside_another_word(pattern, text, exact):
    assert not matches(pattern, text, exact=exact)


def test_exact_matching_still_strips_clitics():
    assert matches("طفله", "الطفلة تنظر", exact=True)


def test_first_match_returns_the_first_pattern_found_in_any_text():
    assert first_match(["هاتف", "phone"], ["كوب", "a phone here"]) == "phone"
    assert first_match(["هاتف"], ["كوب"]) is None
