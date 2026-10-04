"""The English and catch-all hint tables, held to the real workbook so they cannot drift from it."""

from __future__ import annotations

import pytest

from src.arabic import normalize_arabic, search_variants
from src.services.ontology_hints import (
    CATCH_ALL_BY_ARABIC_WORD,
    CATCH_ALL_BY_WORD,
    DEFAULT_CATCH_ALL,
    VISION_LABEL_HINTS,
)
from src.services.ontology_resolver import hint_terms

# These point at a related object because the ontology has no entity for the thing itself.
RELATED_ONLY = {"fruit", "garbage", "trash"}


@pytest.fixture(scope="module")
def labels(real_ontology):
    return {normalize_arabic(row.label_ar): row for row in real_ontology.rows}


@pytest.fixture(scope="module")
def related(real_ontology):
    return {
        normalize_arabic(item)
        for row in real_ontology.rows
        for item in row.related_objects
        if normalize_arabic(item)
    }


def test_every_hint_is_an_entity_label_or_one_of_its_related_objects(labels, related):
    for key, terms in VISION_LABEL_HINTS.items():
        for term in terms:
            variants = search_variants(term)
            assert any(v in labels or v in related for v in variants), (key, term)


def test_the_first_hint_of_a_label_names_an_entity_unless_the_ontology_has_none(labels):
    for key, terms in VISION_LABEL_HINTS.items():
        named = any(v in labels for v in search_variants(terms[0]))
        assert named or key in RELATED_ONLY, (key, terms[0])


def test_a_hint_that_is_only_a_related_object_is_listed_as_such(labels):
    assert {
        key
        for key, terms in VISION_LABEL_HINTS.items()
        if not any(v in labels for v in search_variants(terms[0]))
    } == RELATED_ONLY


@pytest.mark.parametrize("label", ["man", "woman", "boy", "girl", "child", "kid", "baby"])
def test_a_label_about_a_person_stays_generic(label):
    # The product never infers a gender or an age from a photo: these never resolve to more.
    assert set(VISION_LABEL_HINTS[label]) <= {"إنسان", "شخص"}


@pytest.mark.parametrize("label", ["doctor", "nurse", "teacher", "family", "terrorist"])
def test_a_role_is_never_read_from_a_label(label):
    assert label not in VISION_LABEL_HINTS


def test_keys_are_lower_case_english_and_terms_are_arabic():
    for key, terms in VISION_LABEL_HINTS.items():
        assert key == key.lower().strip()
        assert key.isascii()
        assert terms
        assert all(not term.isascii() for term in terms)


def test_every_catch_all_the_tables_name_is_a_catch_all_entity(real_ontology):
    catch_alls = {normalize_arabic(row.label_ar) for row in real_ontology.rows if row.is_catch_all}
    targets = {*CATCH_ALL_BY_WORD.values(), *CATCH_ALL_BY_ARABIC_WORD.values(), DEFAULT_CATCH_ALL}

    assert {normalize_arabic(target) for target in targets} <= catch_alls
    assert DEFAULT_CATCH_ALL == "موقف غير واضح"


def test_every_hint_that_names_a_catch_all_names_a_real_one(real_ontology):
    catch_alls = {normalize_arabic(row.label_ar) for row in real_ontology.rows if row.is_catch_all}

    for terms in VISION_LABEL_HINTS.values():
        for term in terms:
            if "غير" in term.split():
                assert normalize_arabic(term) in catch_alls, term


@pytest.mark.parametrize(
    ("label", "terms"),
    [
        ("cell phone", ("هاتف",)),
        ("  Cell   PHONE ", ("هاتف",)),
        # No hint for the whole label: its last word, then that word without its plural.
        ("old cell phone", ("هاتف",)),
        ("red apples", VISION_LABEL_HINTS["apple"]),
        ("wine glasses", VISION_LABEL_HINTS["glass"]),
        ("cats", VISION_LABEL_HINTS["cat"]),
        ("watches", VISION_LABEL_HINTS["watch"]),
        ("zeppelin", ()),
        ("", ()),
    ],
)
def test_an_english_label_finds_its_arabic_terms(label, terms):
    assert hint_terms(label) == terms


def test_hints_can_be_replaced():
    assert hint_terms("zeppelin", {"zeppelin": ("منطاد",)}) == ("منطاد",)
