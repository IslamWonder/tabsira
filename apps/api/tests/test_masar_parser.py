"""The parser of masar.md: what it takes from the real document, and how it fails on a damaged one."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date

import pytest

from src.schemas.learning_path import SOURCE_ANCHOR, dumps
from src.services.masar_parser import (
    SECTION_7_VOCABULARY,
    MasarParseError,
    _anchors_in,
    _split_references,
    anchor_of,
    parse_masar,
)
from tests.support_ontology import REAL_MASAR

SCRIPTURE_MARKS = re.compile(f"[{chr(0x06D6)}-{chr(0x06ED)}{chr(0xFD3E)}{chr(0xFD3F)}]")


def damaged(text: str, old: str, new: str) -> str:
    """The document with `old` replaced; the replacement must have happened."""
    assert old in text, old
    return text.replace(old, new, 1)


def problems_of(text: str) -> list[str]:
    with pytest.raises(MasarParseError) as error:
        parse_masar(text, source_name="masar.md")
    return list(error.value.problems)


# ─── The real document ───


def test_the_real_document_gives_sixteen_domains_and_ninety_six_units(real_path):
    assert (real_path.counts.domains, real_path.counts.units) == (16, 96)
    assert [d.id for d in real_path.domains] == [f"T{n:02d}" for n in range(16)]
    assert [d.order for d in real_path.domains] == list(range(1, 17))
    assert [u.id for u in real_path.units] == [
        f"T{d:02d}_{n:02d}" for d in range(16) for n in range(1, 7)
    ]
    assert all(u.order == int(u.id[-2:]) and u.domain == u.id[:3] for u in real_path.units)


def test_the_header_of_the_document_becomes_the_version(real_path):
    assert real_path.path_version == "tabsira-masar-1.0"  # v2 section 29: no «h»
    assert (real_path.title, real_path.version) == ("مسار", "1.0")
    assert real_path.source.reference_id == "tabsirah-masar-1.0"  # as the document writes it
    assert real_path.released_on == date(2026, 10, 1)
    assert real_path.description.startswith("ضبط اختيار القيم والمعاني")
    assert real_path.source.file == "docs/spec/masar.md"


def test_the_source_hash_is_the_hash_of_the_document(real_path):
    assert real_path.source.sha256 == hashlib.sha256(REAL_MASAR.read_bytes()).hexdigest()


def test_the_six_depths_are_the_ones_of_the_document(real_path):
    assert [(d.code, d.name) for d in real_path.depths] == [
        ("L0", "الملاحظة"),
        ("L1", "فهم المعنى"),
        ("L2", "معرفة المصدر"),
        ("L3", "التمييز"),
        ("L4", "التطبيق"),
        ("L5", "النقل والتركيب"),
    ]
    assert real_path.depths[2].example == "يميّز معنى الإحياء في الروم 50 عن دعاء المطر"


def test_a_domain_has_its_name_function_goal_and_central_concepts(real_path):
    digital = next(d for d in real_path.domains if d.id == "T08")

    assert digital.title == "العلم والكلمة والحياة الرقمية"
    assert digital.function == "بناء عادات معرفية وتواصلية سليمة"
    assert digital.concepts == ["علم", "تثبت", "خصوصية", "قول سديد", "حوار"]
    assert digital.goal.startswith("نقل أدب العلم والخبر والقول إلى الحياة اليومية")


def test_a_unit_keeps_the_objective_as_the_document_words_it(real_path):
    unit = next(u for u in real_path.units if u.id == "T00_06")

    # The document gives no unit title, and forbids one made by a machine (§5): the objective is the title.
    assert (
        unit.title
        == unit.objectives[0]
        == "يصوغ سؤالًا مفيدًا وينقل مفهومًا إلى مشهد جديد دون تعميم آلي"
    )
    assert unit.prerequisites == ["T00_04", "T00_05"]


def test_a_unit_without_prerequisites_has_none_and_every_unit_has_the_six_depths(real_path):
    first = next(u for u in real_path.units if u.id == "T00_01")

    assert first.prerequisites == []
    assert all(u.depths == ["L0", "L1", "L2", "L3", "L4", "L5"] for u in real_path.units)
    assert next(u for u in real_path.units if u.id == "T15_01").prerequisites == [
        "T04_01",
        "T05_01",
        "T06_01",
    ]


def test_evidence_references_are_text_pointers_with_their_anchors(real_path):
    by_id = {u.id: u for u in real_path.units}

    assert by_id["T00_01"].evidence_refs == ["الإسراء 36", "قاعدة الفصل بين الرصد والتفسير"]
    assert by_id["T00_01"].source_anchors == ["Q:17:36"]
    assert by_id["T12_02"].source_anchors == ["Q:6:99", "H:bukhari:2320"]
    assert by_id["T05_01"].source_anchors == ["H:bukhari:8"]
    # A range, a hadith with a letter, and a plain mention that a link elsewhere spells out.
    assert by_id["T04_05"].evidence_refs == [
        "مسلم 8a",
        "الزلزلة 6\N{EN DASH}8",
        "النساء 13\N{EN DASH}14 مع حفظ سياقها",
    ]
    assert by_id["T04_05"].source_anchors == ["H:muslim:8a", "Q:99:6-8", "Q:4:13-14"]
    # A surah linked by its slug, and a whole surah.
    assert by_id["T03_02"].source_anchors == ["Q:2:2"]
    assert by_id["T02_02"].source_anchors == ["Q:1:5", "Q:112"]


def test_a_unit_whose_references_name_no_text_has_no_anchor(real_path):
    assert [u.id for u in real_path.units if not u.source_anchors] == ["T15_02", "T15_05", "T15_06"]


def test_every_anchor_has_the_form_the_schema_allows_and_every_reference_is_short(real_path):
    for unit in real_path.units:
        assert all(re.fullmatch(SOURCE_ANCHOR, anchor) for anchor in unit.source_anchors), unit.id
        assert all(len(ref) <= 120 for ref in unit.evidence_refs), unit.id


def test_no_text_of_a_verse_or_a_hadith_is_in_the_data(real_path):
    # Quranic marks and the ornate brackets that frame a verse are never in a field.
    for line in dumps(real_path).splitlines():
        assert not SCRIPTURE_MARKS.search(line), line[:80]


def test_only_the_two_units_section_seven_names_have_a_vocabulary(real_path):
    with_concepts = {u.id: u.concepts for u in real_path.units if u.concepts}

    assert with_concepts == {unit: list(words) for unit, words in SECTION_7_VOCABULARY.items()}
    assert with_concepts["T08_03"] == ["التثبت", "خبر", "نقل", "تحقق"]


def test_the_coverage_rules_expand_to_the_units_they_point_at(real_path):
    rules = {rule.asset: rule for rule in real_path.coverage}

    assert len(rules) == 8
    assert rules["الإيمان بالله"].refs == ["T02", "T04_01"]
    assert rules["الإيمان بالله"].units == [f"T02_0{n}" for n in range(1, 7)] + ["T04_01"]
    assert rules["الإيمان بالملائكة والكتب والرسل"].refs == ["T04_02 إلى T04_04"]
    assert rules["الإيمان بالملائكة والكتب والرسل"].units == ["T04_02", "T04_03", "T04_04"]
    assert rules["الشهادتان والصلاة والزكاة والصوم والحج"].units == [
        "T05_01",
        "T05_03",
        "T05_04",
        "T05_05",
        "T05_06",
    ]
    morals = rules["الأخلاق والحقوق والأسرة والعمل والعمران"]
    assert morals.refs == ["T07 إلى T12"]
    assert len(morals.units) == 36 and morals.units[0] == "T07_01" and morals.units[-1] == "T12_06"
    known = {u.id for u in real_path.units}
    assert all(unit in known for rule in real_path.coverage for unit in rule.units)


def test_the_json_is_the_same_bytes_every_time_and_reads_back_as_the_same_data(real_path):
    text = dumps(real_path)

    assert text == dumps(real_path)
    assert text.endswith("}\n")
    document = json.loads(text)
    assert document["path_version"] == "tabsira-masar-1.0"
    assert document["counts"] == {"domains": 16, "units": 96}
    assert len(document["units"]) == 96
    unit_lines = [line for line in text.splitlines() if re.match(r'    \{"id": "T\d\d_\d\d"', line)]
    assert len(unit_lines) == 96
    assert type(real_path).model_validate(document) == real_path


def test_the_path_version_can_be_chosen():
    text = REAL_MASAR.read_text(encoding="utf-8")

    assert (
        parse_masar(text, source_name="x.md", path_version="tabsira-masar-1.1").path_version
        == "tabsira-masar-1.1"
    )


# ─── A damaged document is refused, with the place ───


@pytest.fixture(scope="module")
def text(masar_text):
    return masar_text


def test_a_document_that_is_not_the_reference_lists_what_is_missing():
    problems = problems_of("# شيء آخر\n\nنص.\n")

    assert "The document gives no «معرّف المرجع»." in problems
    assert "The document gives no «الإصدار»." in problems
    assert "The document gives no «التاريخ»." in problems
    assert "No heading contains «ستة أعماق»." in problems
    assert "No heading contains «خريطة المجالات»." in problems
    assert "No heading contains «ضبط التغطية»." in problems


def test_a_document_without_a_title_is_refused(text):
    problems = problems_of(damaged(text, "# مسار\n", "## مسار\n"))

    assert "The document has no title (a heading of level 1)." in problems


def test_a_date_that_is_not_written_day_month_year_is_refused(text):
    problems = problems_of(damaged(text, "1 أكتوبر 2026", "غدا"))

    assert problems == ["The date «غدا» is not of the form «1 أكتوبر 2026»."]


def test_a_depth_row_with_missing_cells_is_refused(text):
    problems = problems_of(
        damaged(
            text,
            "| `L0` | الملاحظة | تعيين شيء أو فعل أو علاقة ظاهرة | يلاحظ وصول الماء إلى تربة فيها نبات |",
            "| `L0` | الملاحظة |",
        )
    )

    assert problems[0].startswith("A depth row is not «code | name | ability | example»")


def test_a_domain_named_differently_in_its_section_is_refused(text):
    problems = problems_of(damaged(text, "### T01 العالم والنعم والتفكر", "### T01 اسم آخر"))

    assert problems == [
        "The domain T01 is «العالم والنعم والتفكر» in the map and «اسم آخر» in its section."
    ]


def test_a_domain_of_the_map_without_a_section_is_refused(text):
    problems = problems_of(damaged(text, "### T02 معرفة الله وتوحيده", "### بدون رمز"))

    assert "The domain T02 is in the map but has no section of units." in problems


def test_a_section_of_units_without_a_row_in_the_map_is_refused(text):
    problems = problems_of(
        damaged(
            text,
            "| `T15` | التركيب والاستقلال في التفكر |",
            "| `T16` | التركيب والاستقلال في التفكر |",
        )
    )

    assert "The section of T15 has no row in the map of domains." in problems


def test_a_section_without_its_goal_is_refused(text):
    problems = problems_of(
        damaged(
            text,
            "**الهدف:** أن يتعلم المستعمل كيف تنتقل المنصة",
            "أن يتعلم المستعمل كيف تنتقل المنصة",
        )
    )

    assert problems == ["The section of T00 has no «الهدف» line."]


def test_units_that_do_not_run_in_order_are_refused(text):
    problems = problems_of(damaged(text, "| `T00_02` |", "| `T00_09` |"))

    assert problems == ["The unit T00_09 stands at place 2 of T00: ids must run in order."]


def test_prerequisites_that_are_not_unit_ids_are_refused(text):
    problems = problems_of(
        damaged(
            text, "| `T00_01` | الإسراء 36، سياسة المصادر", "| ما سبق | الإسراء 36، سياسة المصادر"
        )
    )

    assert len(problems) == 1
    assert problems[0].startswith("The prerequisites of T00_02 are neither «لا شيء» nor unit ids")


def test_a_unit_row_with_too_few_cells_is_refused(text):
    problems = problems_of(
        damaged(
            text,
            "| `T00_01` | يميّز الشيء الظاهر والفعل والعلاقة عن التخمين في النية أو الهوية | لا شيء | [الإسراء 36](https://quran.com/17/36)، قاعدة الفصل بين الرصد والتفسير |",
            "| `T00_01` | يميّز | لا شيء |",
        )
    )

    assert "A unit row of T00 has 3 cells, 4 are expected." in problems


def test_a_link_to_another_site_is_refused(text):
    problems = problems_of(damaged(text, "https://quran.com/17/36", "https://example.com/17/36"))

    assert problems == [
        "The link «الإسراء 36» (https://example.com/17/36) is not a quran.com or sunnah.com address the parser reads."
    ]


def test_a_surah_slug_the_parser_does_not_know_is_refused(text):
    problems = problems_of(
        damaged(text, "https://quran.com/al-baqarah/2", "https://quran.com/al-nisa/2")
    )

    assert len(problems) == 1 and "al-nisa" in problems[0]


def test_one_reference_pointing_at_two_places_is_refused(text):
    problems = problems_of(
        damaged(
            text,
            "الإسراء 36، سياسة المصادر في تبصرة",
            "[الإسراء 36](https://quran.com/17/37)، سياسة المصادر في تبصرة",
        )
    )

    assert problems == ["The reference «الإسراء 36» points at two places: Q:17:36 and Q:17:37."]


def test_a_vocabulary_that_section_seven_no_longer_gives_is_refused(text):
    problems = problems_of(damaged(text, "«التثبت، خبر، نقل، تحقق»", "«التثبت»"))

    assert problems == ["Section 7 no longer gives the vocabulary of T08_03 (خبر, نقل, تحقق)."]


def test_a_vocabulary_for_a_unit_the_document_lacks_is_refused(text):
    problems = problems_of(damaged(text, "| `T08_03` |", "| `T08_09` |"))

    assert any(
        problem.startswith("Section 7 gives a vocabulary for T08_03") for problem in problems
    )


def test_a_coverage_rule_that_names_no_unit_is_refused(text):
    problems = problems_of(damaged(text, "| `T02` و`T04_01` |", "| كل شيء |"))

    assert problems == ["The coverage rule «الإيمان بالله» names no domain or unit: «كل شيء»."]


def test_a_coverage_rule_that_names_a_unit_or_a_domain_that_does_not_exist_is_refused(text):
    unit = problems_of(damaged(text, "| `T02` و`T04_01` |", "| `T02` و`T04_99` |"))
    domain = problems_of(
        damaged(
            text,
            "| الإحسان والنية والإخلاص والتوبة | `T06` |",
            "| الإحسان والنية والإخلاص والتوبة | `T66` |",
        )
    )

    assert unit == ["A coverage rule names T04_99 or T04_99, which does not exist."]
    assert domain == ["A coverage rule names T66 or T66, which does not exist."]


def test_the_counts_the_introduction_states_must_match_the_tables(text):
    problems = problems_of(damaged(text, "16 مجالًا و96 وحدة", "16 مجالًا و95 وحدة"))

    assert problems == [
        "The introduction states 16 domains and 95 units; the tables hold 16 and 96."
    ]


def test_a_field_the_schema_refuses_is_reported_with_its_place(text):
    problems = problems_of(
        damaged(
            text,
            "| `T00_01` | يميّز الشيء الظاهر والفعل والعلاقة عن التخمين في النية أو الهوية |",
            "| `T00_01` |   |",
        )
    )

    assert any(problem.startswith("units.0.title") for problem in problems)


def test_the_error_message_lists_every_problem():
    with pytest.raises(
        MasarParseError,
        match=r"masar\.md cannot be parsed \(\d+ problem\(s\)\):\n  - The document gives no",
    ):
        parse_masar("# x\n", source_name="masar.md")


# ─── Anchors and references, one at a time ───


@pytest.mark.parametrize(
    ("url", "anchor"),
    [
        ("https://quran.com/30/50", "Q:30:50"),
        ("https://quran.com/3/190-191", "Q:3:190-191"),
        ("https://quran.com/112", "Q:112"),
        ("https://quran.com/al-baqarah/2", "Q:2:2"),
        ("https://sunnah.com/muslim:8a", "H:muslim:8a"),
        ("https://sunnah.com/bukhari:2320", "H:bukhari:2320"),
        ("https://quran.com/al-nisa/2", None),
        ("https://sunnah.com/muslim", None),
        ("https://example.com/30/50", None),
        ("not a link", None),
    ],
)
def test_a_reading_link_gives_its_anchor(url, anchor):
    assert anchor_of(url) == anchor


def test_a_reference_cell_is_split_at_its_commas_but_not_inside_a_link_text():
    cell = "[الزمر 53\N{EN DASH}54](https://quran.com/39/53-54)، [آل عمران 159، 160](https://quran.com/3/159-160)، قاعدة"

    assert _split_references(cell) == ["الزمر 53\N{EN DASH}54", "آل عمران 159، 160", "قاعدة"]
    assert _split_references("") == []


def test_a_mention_is_an_anchor_only_when_the_whole_reference_is_the_known_one():
    labels = {"مسلم 8": "H:muslim:8", "مسلم 8a": "H:muslim:8a", "الروم 50": "Q:30:50"}

    assert _anchors_in(["مسلم 8a", "تدريب على الروم 50 و مسلم 8"], labels) == [
        "H:muslim:8a",
        "Q:30:50",
        "H:muslim:8",
    ]
    assert _anchors_in(["مسلم 80"], labels) == []
    assert _anchors_in(["الروم 50", "الروم 50"], labels) == ["Q:30:50"]
    assert _anchors_in(["الروم 50"], {}) == []
