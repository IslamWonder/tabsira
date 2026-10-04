"""The ontology importer: the real workbook, every way a workbook can be broken, and the database load."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from sqlalchemy import func, select, text

from src.models import OntologyEntity
from src.services.ontology_import import (
    MAX_PROBLEMS_SHOWN,
    OntologyImportError,
    export_json,
    load_ontology,
    parse_workbook,
    read_workbook,
    search_forms,
)
from tests.support_ontology import (
    HEADER_ORDER,
    REAL_WORKBOOK,
    good_row,
    workbook_bytes,
)

# The hash recorded in docs/ASSET_MANIFEST.md for data/world-ontology.xlsx.
REAL_SHA256 = "687c3815b5c6daf24154a2ce91bcbfe4cbdb7e49b9633fcf60c38135438ec5c9"


def parse(rows, expected_count=None, **workbook):
    data = workbook_bytes(rows, **workbook)
    count = len(rows) if expected_count is None else expected_count
    return parse_workbook(data, source_name="test.xlsx", expected_count=count)


def problems_of(rows, expected_count=None, **workbook) -> list[str]:
    with pytest.raises(OntologyImportError) as error:
        parse(rows, expected_count, **workbook)
    return list(error.value.problems)


def row_problems(rows, **workbook) -> list[str]:
    """The problems found in the cells of the rows, without the count and id checks that follow."""
    return [problem for problem in problems_of(rows, **workbook) if problem.startswith("Row ")]


# ─── The real workbook ───


def test_the_real_workbook_has_the_thousand_entities_of_the_manifest(real_ontology):
    ids = [row.id for row in real_ontology.rows]

    assert real_ontology.source_name == "world-ontology.xlsx"
    assert real_ontology.source_sha256 == REAL_SHA256
    assert real_ontology.sheet == "الكيان ومفاهيمه"
    assert len(ids) == 1000
    assert ids == [f"E{n:03d}" for n in range(1, 1001)]
    assert len(real_ontology.domains) == 43
    assert real_ontology.warnings == ()


def test_the_hash_is_the_hash_of_the_file_on_disk(real_ontology):
    assert sha256(REAL_WORKBOOK.read_bytes()).hexdigest() == real_ontology.source_sha256


def test_the_first_entity_keeps_its_text_and_its_lists_are_split(real_ontology):
    first = real_ontology.rows[0]

    assert first.id == "E001"
    assert first.label_ar == "سماء"
    assert first.related_objects == ("سماء", "أفق", "شمس", "قمر", "نجوم", "سحاب")
    assert first.actions_and_uses == ("نظر", "رصد", "اهتداء", "حساب المواقيت")
    assert first.contextual_concepts == ("خلق", "تعاقب الليل والنهار", "تأمل", "شكر")
    assert first.special_constraint is None
    assert first.domain == "السماء والطقس"
    assert first.is_catch_all is False
    # The cells exactly as the workbook has them, and where they are.
    assert first.raw == {
        "row": 6,
        "label_ar": "سماء",
        "related_objects": "سماء، أفق، شمس، قمر، نجوم، سحاب",
        "actions_and_uses": "نظر، رصد، اهتداء، حساب المواقيت",
        "contextual_concepts": "خلق، تعاقب الليل والنهار، تأمل، شكر",
        "special_constraint": None,
        "domain": "السماء والطقس",
        "id": "E001",
    }


def test_the_marks_of_the_workbook_are_not_removed(real_ontology):
    # «بَرَد» is written with tashkeel in the workbook; the search form drops them, the text does not.
    hail = next(row for row in real_ontology.rows if row.id == "E008")

    assert hail.label_ar == "بَرَد"
    assert search_forms(hail)[0] == "برد"


def test_every_list_in_the_raw_cells_is_the_joined_list(real_ontology):
    for row in real_ontology.rows:
        for name in ("related_objects", "actions_and_uses", "contextual_concepts"):
            assert "، ".join(getattr(row, name)) == row.raw[name], row.id


def test_the_real_workbook_has_the_eight_constraints_and_thirteen_catch_alls(real_ontology):
    assert real_ontology.constraint_counts == {
        "تأكيد معنى المشهد": 123,
        "لا يُستنتج تشخيص من الصورة": 68,
        "تأكيد الدور أو الصلة": 66,
        "تأكيد الفعل": 46,
        "لا تُستنتج هوية الشخص أو علاقته": 37,
        "تأكيد الفعل التعبدي": 32,
        "تأكيد هوية الشيء أو المكان": 20,
        "تحديد النوع أو الفعل قبل البحث": 13,
    }
    catch_alls = [row for row in real_ontology.rows if row.is_catch_all]
    assert [row.id for row in catch_alls] == [f"E{n}" for n in range(988, 1001)]
    assert {row.label_ar for row in catch_alls} >= {
        "نبات غير محدد",
        "وثيقة غير محددة",
        "موقف غير واضح",
    }


def test_read_workbook_reads_a_file_and_names_it(tmp_path):
    path = tmp_path / "small.xlsx"
    path.write_bytes(workbook_bytes([good_row(1), good_row(2)]))

    parsed = read_workbook(path, expected_count=2)

    assert (parsed.source_name, len(parsed.rows)) == ("small.xlsx", 2)


def test_a_file_that_cannot_be_read_is_an_import_error(tmp_path):
    with pytest.raises(OntologyImportError, match=r"Cannot read .*missing\.xlsx: No such file"):
        read_workbook(tmp_path / "missing.xlsx")


# ─── A broken structure fails clearly ───


def test_a_file_that_is_not_a_workbook_is_refused():
    with pytest.raises(OntologyImportError, match=r"not a readable \.xlsx workbook \(BadZipFile\)"):
        parse_workbook(b"not a zip", source_name="x.xlsx")


def test_a_workbook_without_the_ontology_sheet_names_the_sheets_it_has():
    [problem] = problems_of([good_row(1)], sheet="Sheet1", extra_sheets=["Notes"])

    assert problem == "The sheet «الكيان ومفاهيمه» is missing; the workbook has «Sheet1», «Notes»."


def test_the_sheet_is_found_even_when_a_mark_or_a_hamza_is_spelt_differently():
    parsed = parse([good_row(1)], sheet="الكِيان ومفاهيمه")

    assert len(parsed.rows) == 1


def test_a_sheet_without_a_header_row_is_refused():
    [problem] = problems_of([good_row(1)], headers=["a", "b"])

    assert (
        problem
        == "No header row found in the first 30 rows: a row holding the column «المعرّف» is expected."
    )


def test_a_header_far_below_the_titles_is_not_found():
    [problem] = problems_of([good_row(1)], title_rows=40)

    assert problem.startswith("No header row found in the first 30 rows")


def test_a_missing_column_is_named():
    headers = [name for name in HEADER_ORDER if name != "قيد خاص"]

    [problem] = problems_of([], headers=headers)

    assert problem == "Header row 4: the column «قيد خاص» is missing."


def test_a_column_that_appears_twice_is_refused():
    [problem] = problems_of([], headers=[*HEADER_ORDER, "المجال"])

    assert problem == "Header row 4: the column «المجال» appears more than once."


def test_columns_are_found_by_name_not_by_position():
    reordered = list(reversed(HEADER_ORDER))
    rows = [list(reversed(good_row(1))), list(reversed(good_row(2)))]

    parsed = parse(rows, headers=reordered)

    assert [(row.id, row.domain) for row in parsed.rows] == [
        ("E001", "مجال تجريبي"),
        ("E002", "مجال تجريبي"),
    ]


def test_blank_rows_and_a_title_above_the_header_are_skipped():
    parsed = parse([good_row(1), [], [None] * 7, ["  "] * 7, good_row(2)], 2, title_rows=3)

    assert [row.id for row in parsed.rows] == ["E001", "E002"]
    assert parsed.rows[1].raw["row"] == 10


def test_a_row_shorter_than_the_header_reports_its_empty_cells():
    problems = row_problems([good_row(1)[:1]])

    assert "Row 5, column «الأشياء والموضوعات المتصلة» (B): is empty." in problems
    assert "Row 5, column «المعرّف» (G): is empty." in problems
    assert not any("قيد خاص" in problem for problem in problems)


def test_an_empty_required_cell_names_its_row_and_column():
    problems = row_problems([good_row(1), good_row(2, domain=None), good_row(3, label_ar="   ")])

    assert problems == [
        "Row 6, column «المجال» (F): is empty.",
        "Row 7, column «الكيان أو الشيء» (A): is empty.",
    ]


def test_a_cell_that_is_not_text_is_refused_with_its_type():
    problems = row_problems([good_row(1, related_objects=42), good_row(2, domain=3.5)])

    assert problems == [
        "Row 5, column «الأشياء والموضوعات المتصلة» (B): holds a value of type int, expected text.",
        "Row 6, column «المجال» (F): holds a value of type float, expected text.",
    ]


@pytest.mark.parametrize(
    "bad_id",
    [
        "X001",
        "E01",
        "e001",
        "E00A",
        "E\N{ARABIC-INDIC DIGIT ZERO}\N{ARABIC-INDIC DIGIT ZERO}\N{ARABIC-INDIC DIGIT ONE}",
        "001",
        "E 001",
    ],
)
def test_a_malformed_id_is_named(bad_id):
    problems = row_problems([good_row(1, id=bad_id)])

    assert problems == [f"Row 5, column «المعرّف» (G): «{bad_id}» is not an id of the form E001."]


def test_an_id_with_spaces_around_it_is_accepted_and_trimmed():
    parsed = parse([good_row(1, id=" E001 ")])

    assert parsed.rows[0].id == "E001"
    assert parsed.rows[0].raw["id"] == " E001 "


def test_a_list_cell_with_no_item_is_refused():
    problems = row_problems([good_row(1, actions_and_uses="،، ،")])

    assert problems == ["Row 5, column «الأفعال والاستعمالات» (C): holds no item."]


def test_a_label_without_a_letter_is_refused():
    problems = row_problems([good_row(1, label_ar="- . -")])

    assert problems == ["Row 5, column «الكيان أو الشيء» (A): has no letter."]


def test_a_constraint_the_code_cannot_enforce_is_refused_and_says_where_to_add_it():
    problems = row_problems([good_row(1, special_constraint="لا يُستنتج عمر الشخص من الصورة")])

    assert len(problems) == 1
    assert problems[0].startswith(
        "Row 5, column «قيد خاص» (E): «لا يُستنتج عمر الشخص من الصورة» is a constraint"
    )
    assert "ontology_constraints.KNOWN_CONSTRAINTS" in problems[0]


def test_a_duplicate_id_names_both_rows():
    problems = problems_of([good_row(1), good_row(2), good_row(1, label_ar="شيء آخر")], 2)

    assert "The id E001 is used by 2 rows: 5, 7." in problems
    assert "The sheet has 3 entities, 2 were expected." in problems


def test_a_wrong_row_count_and_gaps_in_the_ids_are_reported_together():
    problems = problems_of([good_row(1), good_row(3)], 3)

    assert problems == [
        "The sheet has 2 entities, 3 were expected.",
        "Ids missing between E001 and E003: E002.",
    ]


def test_ids_outside_the_range_are_reported():
    problems = problems_of([good_row(1), good_row(2), good_row(9)], 3)

    assert problems == [
        "Ids missing between E001 and E003: E003.",
        "Ids outside E001 to E003: E009.",
    ]


def test_a_long_list_of_missing_ids_is_shortened():
    [problem] = problems_of([good_row(1)], 40)[1:]

    assert problem == (
        "Ids missing between E001 and E040: E002, E003, E004, E005, E006, E007, E008, E009, "
        "E010, E011, ... (39 in all)."
    )


def test_every_problem_is_listed_up_to_a_limit_and_the_rest_counted():
    rows = [good_row(number, domain=None) for number in range(1, MAX_PROBLEMS_SHOWN + 6)]

    with pytest.raises(OntologyImportError) as error:
        parse(rows)

    total = len(error.value.problems)
    lines = str(error.value).splitlines()
    assert total > MAX_PROBLEMS_SHOWN
    assert lines[0] == f"The ontology workbook is not valid ({total} problem(s)):"
    assert len(lines) == MAX_PROBLEMS_SHOWN + 2
    assert lines[-1] == f"  - ... and {total - MAX_PROBLEMS_SHOWN} more"


def test_two_entities_with_one_label_are_a_warning_not_an_error():
    parsed = parse([good_row(1, label_ar="كَرسي"), good_row(2, label_ar="كرسي")])

    assert parsed.warnings == ("E002 has the same label as E001: «كرسي».",)


def test_the_number_of_entities_expected_can_be_chosen():
    rows = [good_row(number) for number in range(1, 1201)]

    assert len(parse(rows).rows) == 1200
    with pytest.raises(
        OntologyImportError, match="The sheet has 1200 entities, 1000 were expected"
    ):
        parse_workbook(workbook_bytes(rows), source_name="x.xlsx")


# ─── The generated JSON ───


def test_the_json_carries_the_source_and_every_entity(real_ontology):
    document = json.loads(export_json(real_ontology))

    assert document["source"]["file"] == "world-ontology.xlsx"
    assert document["source"]["sha256"] == REAL_SHA256
    assert document["source"]["entity_count"] == len(document["entities"]) == 1000
    assert len(document["source"]["domains"]) == 43
    assert document["source"]["constraint_counts"]["تحديد النوع أو الفعل قبل البحث"] == 13
    assert document["entities"][0]["id"] == "E001"
    assert document["entities"][-1]["label_ar"] == "موقف غير واضح"
    assert document["entities"][-1]["is_catch_all"] is True


def test_the_json_is_the_same_bytes_every_time_and_has_one_entity_per_line(real_ontology):
    once = export_json(real_ontology)

    assert once == export_json(real_ontology)
    assert once.endswith("}\n")
    assert len([line for line in once.splitlines() if line.startswith('    {"id": "E')]) == 1000
    assert "\\u" not in once  # Arabic is written as Arabic, not as escapes


# ─── The database ───


def test_the_search_forms_leave_marks_and_hamzas_out_and_keep_each_term_once():
    row = parse([good_row(1, label_ar="أَرْض", related_objects="أرض، تُرْبة، أرض، حقل زراعي")]).rows[0]

    assert search_forms(row) == ("ارض", ["ارض", "تربه", "حقل زراعي"], "ارض تربه حقل زراعي")


async def test_the_real_ontology_loads_with_its_text_arrays_and_search_forms(
    db_session, real_ontology
):
    result = await load_ontology(db_session, real_ontology)

    assert (result.inserted, result.updated, result.removed) == (1000, 0, 0)
    assert await db_session.scalar(select(func.count()).select_from(OntologyEntity)) == 1000
    stored = await db_session.get(OntologyEntity, "E008")
    assert stored.label_ar == "بَرَد"
    assert stored.label_norm == "برد"
    assert stored.related_objects[0] == "بَرَد"
    assert stored.related_norm[0] == "برد"
    assert stored.search_text.startswith("برد ")
    assert stored.raw["row"] == 13
    assert stored.source_sha256 == REAL_SHA256
    assert stored.imported_at is not None
    catch_all = await db_session.scalar(
        select(func.count()).where(OntologyEntity.is_catch_all.is_(True))
    )
    assert catch_all == 13


async def test_loading_the_same_file_again_updates_every_entity_and_adds_none(
    db_session, real_ontology
):
    await load_ontology(db_session, real_ontology)

    again = await load_ontology(db_session, real_ontology)

    assert (again.inserted, again.updated, again.removed) == (0, 1000, 0)
    assert await db_session.scalar(select(func.count()).select_from(OntologyEntity)) == 1000


async def test_loading_a_new_version_adds_changes_and_removes_entities(db_session):
    first = parse([good_row(1), good_row(2), good_row(3)])
    second = parse([good_row(1, label_ar="شيء معدل"), good_row(2), good_row(3), good_row(4)], 4)
    third = parse([good_row(1), good_row(2)], 2)

    await load_ontology(db_session, first)
    grown = await load_ontology(db_session, second)
    shrunk = await load_ontology(db_session, third)

    assert (grown.inserted, grown.updated, grown.removed) == (1, 3, 0)
    assert (shrunk.inserted, shrunk.updated, shrunk.removed) == (0, 2, 2)
    remaining = (
        await db_session.scalars(select(OntologyEntity.id).order_by(OntologyEntity.id))
    ).all()
    assert remaining == ["E001", "E002"]
    assert (await db_session.get(OntologyEntity, "E001")).label_ar == "شيء 1"


async def test_a_load_is_split_in_batches_below_the_parameter_limit(db_session, monkeypatch):
    from src.services import ontology_import

    monkeypatch.setattr(ontology_import, "ROWS_PER_INSERT", 2)
    parsed = parse([good_row(number) for number in range(1, 6)])

    result = await load_ontology(db_session, parsed)

    assert result.inserted == 5
    assert await db_session.scalar(text("SELECT count(*) FROM corpus.ontology_entities")) == 5
