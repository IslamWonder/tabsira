"""Loading a learning path version: new, again, a newer release, and a replacement."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import func, select

from src.models import (
    LearnerUnitState,
    LearningDomain,
    LearningPathVersion,
    LearningUnit,
)
from src.schemas.learning_path import LearningPathFile, dumps
from src.services.masar_import import (
    LoadStatus,
    PathVersionConflictError,
    import_path,
)

GUEST = "g" * 24


def digest(path: LearningPathFile) -> str:
    return hashlib.sha256(dumps(path).encode()).hexdigest()


def released(path: LearningPathFile, path_version: str, **fields) -> LearningPathFile:
    """The same path under another version, with some top-level fields changed."""
    return LearningPathFile.model_validate(
        {**path.model_dump(mode="json"), "path_version": path_version, **fields}
    )


async def load(session, path, **options):
    return await import_path(
        session, path, source_file="path.json", source_sha256=digest(path), **options
    )


async def count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def active_versions(session) -> list[str]:
    return list(
        (
            await session.scalars(
                select(LearningPathVersion.path_version)
                .where(LearningPathVersion.is_active.is_(True))
                .order_by(LearningPathVersion.path_version)
            )
        ).all()
    )


# ─── A first version ───


async def test_a_first_version_is_loaded_with_its_domains_and_units_and_becomes_active(
    db_session, real_path
):
    result = await load(db_session, real_path)

    assert (result.path_version, result.status) == ("tabsira-masar-1.0", LoadStatus.CREATED)
    assert (result.domains, result.units, result.active) == (16, 96, True)
    assert await count(db_session, LearningDomain) == 16
    assert await count(db_session, LearningUnit) == 96
    assert await active_versions(db_session) == ["tabsira-masar-1.0"]


async def test_the_version_row_holds_what_the_file_says_about_itself(db_session, real_path):
    await load(db_session, real_path)

    stored = await db_session.get(LearningPathVersion, "tabsira-masar-1.0")

    assert (stored.title, stored.version, str(stored.released_on)) == ("مسار", "1.0", "2026-10-01")
    assert stored.description.startswith("ضبط اختيار القيم")
    assert (stored.domain_count, stored.unit_count) == (16, 96)
    assert (stored.source_file, stored.source_sha256) == ("path.json", digest(real_path))
    assert [d["code"] for d in stored.depths] == ["L0", "L1", "L2", "L3", "L4", "L5"]
    assert len(stored.coverage) == 8
    assert stored.coverage[0]["asset"] == "الإيمان بالله"
    assert stored.imported_at is not None


async def test_domains_and_units_keep_their_text_order_and_arrays(db_session, real_path):
    await load(db_session, real_path)

    domain = await db_session.get(LearningDomain, ("tabsira-masar-1.0", "T08"))
    unit = await db_session.get(LearningUnit, ("tabsira-masar-1.0", "T12_02"))

    assert (domain.position, domain.title) == (9, "العلم والكلمة والحياة الرقمية")
    assert domain.concepts == ["علم", "تثبت", "خصوصية", "قول سديد", "حوار"]
    assert (unit.domain_id, unit.position) == ("T12", 2)
    assert unit.title == "يميز إنبات النبات عن فعل الإنسان الذي يغرس وينتفع بغرسه غيره"
    assert unit.objectives == [unit.title]
    assert unit.prerequisites == ["T01_03"]
    assert unit.depths == ["L0", "L1", "L2", "L3", "L4", "L5"]
    assert unit.concepts == ["إنبات", "غرس الإنسان", "الانتفاع بالغرس"]
    assert unit.evidence_refs == ["الأنعام 99", "البخاري 2320"]
    assert unit.source_anchors == ["Q:6:99", "H:bukhari:2320"]


async def test_a_first_version_can_be_loaded_without_being_activated(db_session, real_path):
    result = await load(db_session, real_path, activate=False)

    assert result.active is False
    assert await active_versions(db_session) == []


# ─── The same file, and a newer release ───


async def test_the_same_file_again_changes_nothing(db_session, real_path):
    await load(db_session, real_path)
    before = (await db_session.get(LearningPathVersion, "tabsira-masar-1.0")).imported_at

    again = await load(db_session, real_path)

    assert (again.status, again.active) == (LoadStatus.UNCHANGED, True)
    assert await count(db_session, LearningUnit) == 96
    assert (await db_session.get(LearningPathVersion, "tabsira-masar-1.0")).imported_at == before


async def test_a_newer_release_is_added_next_to_the_first_and_waits_to_be_activated(
    db_session, real_path
):
    await load(db_session, real_path)

    result = await load(db_session, released(real_path, "tabsira-masar-1.1", version="1.1"))

    assert (result.status, result.active) == (LoadStatus.CREATED, False)
    assert await count(db_session, LearningPathVersion) == 2
    assert await count(db_session, LearningUnit) == 192
    assert await active_versions(db_session) == ["tabsira-masar-1.0"]


async def test_activating_a_release_switches_the_active_version(db_session, real_path):
    newer = released(real_path, "tabsira-masar-1.1", version="1.1")
    await load(db_session, real_path)
    await load(db_session, newer)

    result = await load(db_session, newer, activate=True)

    assert (result.status, result.active) == (LoadStatus.UNCHANGED, True)
    assert await active_versions(db_session) == ["tabsira-masar-1.1"]

    back = await load(db_session, real_path, activate=True)

    assert back.active is True
    assert await active_versions(db_session) == ["tabsira-masar-1.0"]


async def test_a_release_loaded_with_activate_true_takes_over_at_once(db_session, real_path):
    await load(db_session, real_path)

    result = await load(db_session, released(real_path, "tabsira-masar-1.1"), activate=True)

    assert result.active is True
    assert await active_versions(db_session) == ["tabsira-masar-1.1"]


async def test_a_release_with_a_new_domain_and_unit_needs_no_change_in_the_code(
    db_session, real_path
):
    data = real_path.model_dump(mode="json")
    data["domains"].append(
        {**data["domains"][-1], "id": "T16", "order": 17, "title": "مجال جديد", "concepts": []}
    )
    data["units"].append(
        {
            **data["units"][-1],
            "id": "T16_01",
            "domain": "T16",
            "order": 1,
            "prerequisites": ["T00_01"],
        }
    )
    data["counts"] = {"domains": 17, "units": 97}
    grown = LearningPathFile.model_validate({**data, "path_version": "tabsira-masar-1.1"})
    await load(db_session, real_path)

    result = await load(db_session, grown)

    assert (result.domains, result.units) == (17, 97)
    assert await db_session.get(LearningUnit, ("tabsira-masar-1.1", "T16_01")) is not None
    assert await count(db_session, LearningUnit) == 96 + 97


# ─── Replacing a published version ───


async def test_another_file_for_a_published_version_is_refused(db_session, real_path):
    await load(db_session, real_path)
    edited = released(real_path, "tabsira-masar-1.0", title="مسار معدّل")

    with pytest.raises(PathVersionConflictError, match="already published with other content"):
        await load(db_session, edited)

    stored = await db_session.get(LearningPathVersion, "tabsira-masar-1.0")
    assert stored.title == "مسار"


async def test_a_replacement_changes_the_version_and_drops_what_the_file_no_longer_has(
    db_session, real_path
):
    await load(db_session, real_path)
    data = real_path.model_dump(mode="json")
    data["units"] = [u for u in data["units"] if u["id"] != "T15_06"]
    data["counts"] = {"domains": 16, "units": 95}
    data["title"] = "مسار معدّل"
    smaller = LearningPathFile.model_validate(data)

    result = await load(db_session, smaller, replace=True)

    assert (result.status, result.units) == (LoadStatus.REPLACED, 95)
    db_session.expire_all()
    assert (await db_session.get(LearningPathVersion, "tabsira-masar-1.0")).title == "مسار معدّل"
    assert await count(db_session, LearningUnit) == 95
    assert await db_session.get(LearningUnit, ("tabsira-masar-1.0", "T15_06")) is None


async def test_a_replacement_can_drop_a_whole_domain(db_session, real_path):
    await load(db_session, real_path)
    data = real_path.model_dump(mode="json")
    data["domains"] = [d for d in data["domains"] if d["id"] != "T15"]
    data["units"] = [u for u in data["units"] if u["domain"] != "T15"]
    data["counts"] = {"domains": 15, "units": 90}
    data["coverage"] = []
    data["units"] = [
        {**u, "prerequisites": [p for p in u["prerequisites"] if not p.startswith("T15")]}
        for u in data["units"]
    ]

    result = await load(db_session, LearningPathFile.model_validate(data), replace=True)

    assert (result.domains, result.units) == (15, 90)
    assert await count(db_session, LearningDomain) == 15


async def test_a_replacement_is_refused_while_a_learner_has_state_for_a_unit_it_drops(
    db_session, real_path
):
    await load(db_session, real_path)
    db_session.add(
        LearnerUnitState(
            guest_key=GUEST, path_version="tabsira-masar-1.0", unit_id="T15_06", seen_count=1
        )
    )
    await db_session.flush()
    data = real_path.model_dump(mode="json")
    data["units"] = [u for u in data["units"] if u["id"] != "T15_06"]
    data["counts"] = {"domains": 16, "units": 95}

    with pytest.raises(PathVersionConflictError, match="Learners have state for units"):
        await load(db_session, LearningPathFile.model_validate(data), replace=True)

    # The refusal rolled back its own work only: the session is usable and nothing was lost.
    assert await count(db_session, LearningUnit) == 96
    assert await count(db_session, LearnerUnitState) == 1


async def test_a_replacement_keeps_the_state_of_the_units_it_keeps(db_session, real_path):
    await load(db_session, real_path)
    db_session.add(
        LearnerUnitState(guest_key=GUEST, path_version="tabsira-masar-1.0", unit_id="T00_01")
    )
    await db_session.flush()

    await load(
        db_session, released(real_path, "tabsira-masar-1.0", title="مسار معدّل"), replace=True
    )

    assert await count(db_session, LearnerUnitState) == 1


async def test_a_replacement_of_the_active_version_leaves_it_active(db_session, real_path):
    await load(db_session, real_path)

    result = await load(
        db_session, released(real_path, "tabsira-masar-1.0", title="مسار معدّل"), replace=True
    )

    assert result.active is True
    assert await active_versions(db_session) == ["tabsira-masar-1.0"]
