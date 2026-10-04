"""The learning path validator: a good file passes, and each way of breaking one is named."""

from __future__ import annotations

import json

import pytest

from src.schemas.learning_path import LearningPathFile, dumps
from src.services.masar_validator import (
    MAX_PROBLEMS_SHOWN,
    LearningPathError,
    load_path,
    read_path,
    validate_path,
)

# What the ornate brackets and the marks of Quranic text are made of; never written in the data.
ORNATE_LEFT = chr(0xFD3E)
SMALL_MARK = chr(0x06D6)


def changed(path: LearningPathFile, **top) -> LearningPathFile:
    """A copy of the file with some top-level fields replaced."""
    return LearningPathFile.model_validate({**path.model_dump(mode="json"), **top})


def with_unit(path: LearningPathFile, unit_id: str, **fields) -> LearningPathFile:
    units = [
        {**unit.model_dump(mode="json"), **(fields if unit.id == unit_id else {})}
        for unit in path.units
    ]
    return changed(path, units=units)


def problems_of(path: LearningPathFile, **expect) -> list[str]:
    with pytest.raises(LearningPathError) as error:
        validate_path(path, **expect)
    return list(error.value.problems)


# ─── A valid file ───


def test_the_real_path_is_valid_and_has_sixteen_domains_and_ninety_six_units(real_path):
    validate_path(real_path, expected_domains=16, expected_units=96)


def test_what_a_release_must_hold_can_be_stated(real_path):
    problems = problems_of(real_path, expected_domains=17, expected_units=100)

    assert problems == [
        "17 domains were expected, the file holds 16.",
        "100 units were expected, the file holds 96.",
    ]


def test_the_counts_a_file_declares_must_be_the_counts_it_holds(real_path):
    wrong = changed(real_path, counts={"domains": 15, "units": 95})

    assert problems_of(wrong) == [
        "The file declares 15 domains and holds 16.",
        "The file declares 95 units and holds 96.",
    ]


# ─── Ids, orders, domains and depths ───


def test_a_domain_that_appears_twice_or_a_depth_defined_twice_is_named(real_path):
    data = real_path.model_dump(mode="json")
    wrong = changed(
        real_path,
        domains=[*data["domains"], {**data["domains"][0], "order": 17}],
        depths=[*data["depths"], data["depths"][0]],
        counts={"domains": 17, "units": 96},
    )

    problems = problems_of(wrong)

    assert "Domain T00 appears more than once." in problems
    assert "Depth L0 is defined more than once." in problems


def test_a_gap_in_the_domain_orders_is_named(real_path):
    domains = [
        {**d.model_dump(mode="json"), "order": d.order + (d.order > 3)} for d in real_path.domains
    ]

    problems = problems_of(changed(real_path, domains=domains))

    assert problems[0].startswith("The domain orders do not run from 1 without a gap")


def test_a_unit_that_appears_twice_is_named(real_path):
    data = real_path.model_dump(mode="json")
    wrong = changed(
        real_path, units=[*data["units"], data["units"][0]], counts={"domains": 16, "units": 97}
    )

    assert "Unit T00_01 appears more than once." in problems_of(wrong)


def test_a_unit_of_a_domain_the_file_does_not_have_is_named(real_path):
    problems = problems_of(with_unit(real_path, "T00_01", domain="T77"))

    assert "Unit T00_01 belongs to T77, which is not a domain of the file." in problems
    assert "Domain T00 has no unit." not in problems


def test_a_unit_must_be_named_after_its_domain_and_its_order(real_path):
    problems = problems_of(with_unit(real_path, "T00_01", domain="T01", order=1))

    assert "Unit T00_01 is not named after its domain T01." in problems
    # T01 now has two units at order 1 and none was lost from T00's count of orders.
    assert any(p.startswith("The unit orders of T01 do not run") for p in problems)
    assert any(p.startswith("The unit orders of T00 do not run") for p in problems)

    problems = problems_of(with_unit(real_path, "T00_01", order=5))

    assert "Unit T00_01 is at order 5, which its id does not say." in problems


def test_a_unit_may_only_list_depths_the_file_defines_and_each_once(real_path):
    problems = problems_of(with_unit(real_path, "T00_02", depths=["L0", "L9", "L0"]))

    assert "Unit T00_02 lists depths the file does not define: L9." in problems
    assert "Unit T00_02 lists a depth twice." in problems


def test_a_domain_without_units_is_named(real_path):
    units = [u.model_dump(mode="json") for u in real_path.units if u.domain != "T15"]
    wrong = changed(
        real_path,
        units=units,
        counts={"domains": 16, "units": len(units)},
        coverage=[],
    )

    problems = problems_of(wrong)

    assert "Domain T15 has no unit." in problems
    # The prerequisites that pointed into T15 are not in the file either.
    assert not any("prerequisite" in p and "T15" not in p for p in problems)


# ─── Prerequisites ───


def test_a_prerequisite_must_be_a_unit_of_the_file(real_path):
    problems = problems_of(with_unit(real_path, "T00_02", prerequisites=["T00_01", "T99_01"]))

    assert problems == ["Unit T00_02 has the prerequisite T99_01, which is not a unit of the file."]


def test_a_unit_cannot_be_its_own_prerequisite_or_list_one_twice(real_path):
    problems = problems_of(
        with_unit(real_path, "T00_02", prerequisites=["T00_02", "T00_01", "T00_01"])
    )

    assert "Unit T00_02 is its own prerequisite." in problems
    assert "Unit T00_02 lists a prerequisite twice." in problems


def test_a_cycle_of_prerequisites_is_found_and_shown(real_path):
    # T00_01 waits for T00_04, which waits for T00_02, which waits for T00_01.
    wrong = with_unit(real_path, "T00_01", prerequisites=["T00_04"])

    [problem] = problems_of(wrong)

    assert problem == "The prerequisites form a cycle: T00_01 -> T00_04 -> T00_02 -> T00_01."


def test_a_cycle_of_two_units_is_found(real_path):
    wrong = with_unit(real_path, "T00_01", prerequisites=["T00_02"])

    [problem] = problems_of(wrong)

    assert problem == "The prerequisites form a cycle: T00_01 -> T00_02 -> T00_01."


def test_a_diamond_of_prerequisites_is_not_a_cycle(real_path):
    # T00_06 already needs T00_04 and T00_05, which both lead back to T00_04: shared, not circular.
    assert real_path.units[5].prerequisites == ["T00_04", "T00_05"]
    validate_path(real_path)


# ─── References and coverage ───


def test_a_reference_that_is_a_quotation_is_refused(real_path):
    too_long = "ك" * 121
    marked = f"{ORNATE_LEFT}نص{SMALL_MARK}"

    long_problem = problems_of(with_unit(real_path, "T00_02", evidence_refs=[too_long]))
    mark_problem = problems_of(with_unit(real_path, "T00_02", evidence_refs=[marked]))

    assert long_problem == [
        "Unit T00_02 has a reference that is not a pointer: «" + "ك" * 40 + "...»."
    ]
    assert mark_problem[0].startswith("Unit T00_02 has a reference that is not a pointer")


def test_a_source_anchor_listed_twice_is_named(real_path):
    problems = problems_of(with_unit(real_path, "T00_02", source_anchors=["Q:17:36", "Q:17:36"]))

    assert problems == ["Unit T00_02 lists a source anchor twice."]


def test_a_coverage_rule_must_point_at_units_that_exist(real_path):
    data = real_path.model_dump(mode="json")
    rule = {**data["coverage"][0], "units": ["T02_01", "T88_01"]}

    problems = problems_of(changed(real_path, coverage=[rule, *data["coverage"][1:]]))

    assert problems == ["The coverage rule «الإيمان بالله» names units that do not exist: T88_01."]


def test_the_message_lists_the_problems_up_to_a_limit(real_path):
    units = [
        {**unit.model_dump(mode="json"), "prerequisites": ["T99_01"]} for unit in real_path.units
    ]

    with pytest.raises(LearningPathError) as error:
        validate_path(changed(real_path, units=units))

    lines = str(error.value).splitlines()
    assert lines[0] == "The learning path file is not valid (96 problem(s)):"
    assert len(lines) == MAX_PROBLEMS_SHOWN + 2
    assert lines[-1] == f"  - ... and {96 - MAX_PROBLEMS_SHOWN} more"


# ─── Loading a file ───


def test_a_file_is_read_back_as_the_data_it_was_written_from(real_path):
    assert load_path(dumps(real_path)) == real_path


def test_text_that_is_not_json_is_refused_with_its_line():
    with pytest.raises(LearningPathError, match=r"Not JSON: .* at line 2\."):
        load_path('{\n  "path_version": }')


def test_a_file_of_the_wrong_shape_is_refused_with_the_field(real_path):
    document = real_path.model_dump(mode="json")
    document["stray"] = 1
    del document["title"]
    document["units"][0]["id"] = "unit one"

    with pytest.raises(LearningPathError) as error:
        load_path(json.dumps(document))

    problems = "\n".join(error.value.problems)
    assert "stray: Extra inputs are not permitted" in problems
    assert "title: Field required" in problems
    assert "units.0.id: String should match pattern" in problems


def test_a_document_that_is_not_an_object_is_refused():
    with pytest.raises(LearningPathError, match="file: Input should be a valid dictionary"):
        load_path("[]")


def test_read_path_reads_validates_and_names_a_missing_file(tmp_path, real_path):
    good = tmp_path / "good.json"
    good.write_text(dumps(real_path), encoding="utf-8")

    assert read_path(good, expected_domains=16, expected_units=96) == real_path
    with pytest.raises(LearningPathError, match=r"Cannot read .*absent\.json: No such file"):
        read_path(tmp_path / "absent.json")
    with pytest.raises(LearningPathError, match="17 domains were expected"):
        read_path(good, expected_domains=17)
