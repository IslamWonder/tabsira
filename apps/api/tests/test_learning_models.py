"""The learning path and learner state tables: versions, domains, units and what a learner did with them."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from src.models import (
    Base,
    LearnerUnitState,
    LearningDomain,
    LearningPathVersion,
    LearningUnit,
    User,
)

SHA = "0" * 64
GUEST = "g" * 24


def version(path_version: str = "tabsira-masar-1.0", **columns) -> LearningPathVersion:
    values = {
        "path_version": path_version,
        "title": "مسار",
        "version": "1.0",
        "source_file": "tabsira-masar-1.0.json",
        "source_sha256": SHA,
        "domain_count": 1,
        "unit_count": 1,
        "depths": [],
        "coverage": [],
    }
    return LearningPathVersion(**{**values, **columns})


def domain(path_version: str = "tabsira-masar-1.0", domain_id: str = "T00", **columns):
    values = {
        "path_version": path_version,
        "id": domain_id,
        "position": 1,
        "title": "مفاتيح النظر والتعلم",
        "function": "ضبط الانتقال من الصورة إلى المعرفة",
        "goal": "أن يتعلم المستعمل كيف تنتقل المنصة من المرئي إلى المعنى",
        "concepts": ["ملاحظة", "دليل"],
    }
    return LearningDomain(**{**values, **columns})


def unit(path_version: str = "tabsira-masar-1.0", unit_id: str = "T00_01", **columns):
    values = {
        "path_version": path_version,
        "id": unit_id,
        "domain_id": "T00",
        "position": 1,
        "title": "يميّز الشيء الظاهر عن التخمين",
        "objectives": ["يميّز الشيء الظاهر عن التخمين"],
        "prerequisites": [],
        "depths": ["L0", "L1"],
        "concepts": [],
        "evidence_refs": ["الإسراء 36"],
        "source_anchors": ["Q:17:36"],
    }
    return LearningUnit(**{**values, **columns})


@pytest.fixture
async def path(db_session):
    """One version with its domain and its first unit, flushed."""
    db_session.add(version())
    await db_session.flush()
    db_session.add(domain())
    await db_session.flush()
    db_session.add(unit())
    await db_session.flush()
    return db_session


def state(**columns) -> LearnerUnitState:
    values = {"guest_key": GUEST, "path_version": "tabsira-masar-1.0", "unit_id": "T00_01"}
    return LearnerUnitState(**{**values, **columns})


async def account(session) -> uuid.UUID:
    """An account, flushed, whose id a state can name."""
    user = User(email=f"{uuid.uuid4()}@example.com", display_name="Reader")
    session.add(user)
    await session.flush()
    return user.id


def test_every_table_lives_in_the_app_schema():
    assert {
        "app.learning_path_versions",
        "app.learning_domains",
        "app.learning_units",
        "app.learner_unit_states",
    } <= set(Base.metadata.tables)


# ─── The path ───


async def test_a_version_keeps_its_depths_and_coverage_and_starts_inactive(db_session):
    db_session.add(
        version(
            depths=[{"code": "L0", "name": "الملاحظة"}],
            coverage=[{"asset": "الإيمان بالله", "units": ["T02_01"]}],
        )
    )
    await db_session.flush()

    stored = await db_session.scalar(select(LearningPathVersion))

    assert stored.depths == [{"code": "L0", "name": "الملاحظة"}]
    assert stored.coverage[0]["asset"] == "الإيمان بالله"
    assert stored.is_active is False
    assert stored.released_on is None
    assert stored.imported_at is not None


async def test_only_one_version_is_active_at_a_time(db_session):
    db_session.add_all([version("tabsira-masar-1.0", is_active=True), version("tabsira-masar-1.1")])
    await db_session.flush()
    stored = await db_session.get(LearningPathVersion, "tabsira-masar-1.1")
    stored.is_active = True

    with pytest.raises(IntegrityError, match="uq_learning_path_versions_active"):
        await db_session.flush()


async def test_a_unit_keeps_its_arrays_and_belongs_to_its_domain_and_version(path):
    stored = await path.scalar(select(LearningUnit))

    assert (stored.path_version, stored.id, stored.domain_id) == (
        "tabsira-masar-1.0",
        "T00_01",
        "T00",
    )
    assert stored.objectives == ["يميّز الشيء الظاهر عن التخمين"]
    assert (stored.prerequisites, stored.concepts) == ([], [])
    assert stored.depths == ["L0", "L1"]
    assert (stored.evidence_refs, stored.source_anchors) == (["الإسراء 36"], ["Q:17:36"])


async def test_the_same_ids_can_live_in_two_versions(path):
    path.add(version("tabsira-masar-1.1"))
    await path.flush()
    path.add(domain("tabsira-masar-1.1"))
    await path.flush()
    path.add(unit("tabsira-masar-1.1", title="صياغة أحدث"))
    await path.flush()

    titles = (
        await path.scalars(select(LearningUnit.title).where(LearningUnit.id == "T00_01"))
    ).all()

    assert sorted(titles) == sorted(["يميّز الشيء الظاهر عن التخمين", "صياغة أحدث"])


async def test_a_unit_needs_a_domain_of_its_own_version(path):
    path.add(version("tabsira-masar-1.1"))
    await path.flush()
    path.add(unit("tabsira-masar-1.1"))  # the domain T00 exists only in 1.0

    with pytest.raises(IntegrityError, match="fk_learning_units_domain"):
        await path.flush()


async def test_a_position_is_used_once_per_domain_and_per_version(path):
    path.add(unit(unit_id="T00_02", position=1))

    with pytest.raises(IntegrityError, match="uq_learning_units_position"):
        await path.flush()


async def test_two_domains_of_a_version_cannot_share_a_position(path):
    path.add(domain(domain_id="T01", position=1))

    with pytest.raises(IntegrityError, match="uq_learning_domains_position"):
        await path.flush()


@pytest.mark.parametrize("model", ["domain", "unit"])
async def test_a_position_starts_at_one(path, model):
    path.add(
        domain(domain_id="T01", position=0)
        if model == "domain"
        else unit(unit_id="T00_02", position=0)
    )

    with pytest.raises(IntegrityError, match="position_positive"):
        await path.flush()


async def test_deleting_a_version_removes_its_domains_and_units(path):
    await path.execute(text("DELETE FROM app.learning_path_versions"))

    for table in ("learning_domains", "learning_units"):
        count = await path.scalar(select(func.count()).select_from(text(f"app.{table}")))
        assert count == 0, table


# ─── The learner's state ───


async def test_a_state_starts_at_zero_and_is_owned_by_a_guest(path):
    path.add(state())
    await path.flush()

    stored = await path.scalar(select(LearnerUnitState))

    assert (stored.seen_count, stored.opened_count, stored.completed_count) == (0, 0, 0)
    assert (stored.user_id, stored.guest_key) == (None, GUEST)
    assert stored.created_at <= stored.last_at


async def test_a_state_can_belong_to_an_account(path):
    owner = await account(path)
    path.add(state(guest_key=None, user_id=owner, seen_count=3, opened_count=2, completed_count=1))
    await path.flush()

    stored = await path.scalar(select(LearnerUnitState))

    assert (stored.user_id, stored.guest_key) == (owner, None)
    assert (stored.seen_count, stored.opened_count, stored.completed_count) == (3, 2, 1)


@pytest.mark.parametrize(
    "owners",
    [{"guest_key": None}, {"guest_key": GUEST, "user_id": "an account"}],
    ids=["no owner", "two owners"],
)
async def test_a_state_has_exactly_one_owner(path, owners):
    if owners.get("user_id") == "an account":
        owners = {**owners, "user_id": await account(path)}
    path.add(state(**owners))

    with pytest.raises(IntegrityError, match="one_owner"):
        await path.flush()


@pytest.mark.parametrize("key", ["", "short", "k" * 15])
async def test_a_guest_key_is_an_opaque_key_that_is_not_guessable_short(path, key):
    path.add(state(guest_key=key))

    with pytest.raises(IntegrityError, match="guest_key_length"):
        await path.flush()


@pytest.mark.parametrize("column", ["seen_count", "opened_count", "completed_count"])
async def test_a_count_is_never_negative(path, column):
    path.add(state(**{column: -1}))

    with pytest.raises(IntegrityError, match="counts_not_negative"):
        await path.flush()


async def test_a_guest_has_one_state_per_unit_of_a_version_and_an_account_too(path):
    owner = await account(path)
    path.add_all([state(), state(guest_key=None, user_id=owner)])
    await path.flush()
    # The same guest on the same unit of another version, or another guest, is a different row.
    path.add(version("tabsira-masar-1.1"))
    await path.flush()
    path.add(domain("tabsira-masar-1.1"))
    await path.flush()
    path.add(unit("tabsira-masar-1.1"))
    await path.flush()
    path.add_all([state(path_version="tabsira-masar-1.1"), state(guest_key="h" * 24)])
    await path.flush()

    assert await path.scalar(select(func.count()).select_from(LearnerUnitState)) == 4

    path.add(state())
    with pytest.raises(IntegrityError, match="uq_learner_unit_states_guest"):
        await path.flush()


async def test_an_account_has_one_state_per_unit_of_a_version(path):
    owner = await account(path)
    path.add(state(guest_key=None, user_id=owner))
    await path.flush()
    path.add(state(guest_key=None, user_id=owner))

    with pytest.raises(IntegrityError, match="uq_learner_unit_states_user"):
        await path.flush()


async def test_a_state_names_an_account_that_exists(path):
    path.add(state(guest_key=None, user_id=uuid.uuid4()))

    with pytest.raises(IntegrityError, match="fk_learner_unit_states_user_id_users"):
        await path.flush()


async def test_deleting_an_account_deletes_its_learning_state_and_only_its_own(path):
    owner, other = await account(path), await account(path)
    path.add_all(
        [
            state(guest_key=None, user_id=owner, completed_count=2),
            state(guest_key=None, user_id=other),
            state(),
        ]
    )
    await path.flush()

    await path.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": owner})

    remaining = (await path.scalars(select(LearnerUnitState.user_id))).all()
    assert sorted(map(str, remaining), key=str) == sorted([str(other), "None"], key=str)


async def test_a_state_names_a_unit_that_exists_in_that_version(path):
    path.add(state(unit_id="T99_99"))

    with pytest.raises(IntegrityError, match="fk_learner_unit_states_unit"):
        await path.flush()


async def test_a_unit_that_learners_have_state_for_cannot_be_deleted_from_under_them(path):
    path.add(state())
    await path.flush()

    with pytest.raises(IntegrityError, match="fk_learner_unit_states_unit"):
        await path.execute(text("DELETE FROM app.learning_units"))


async def test_the_database_says_that_completed_is_not_mastery(path):
    comment = await path.scalar(
        text(
            "SELECT col_description('app.learner_unit_states'::regclass, "
            "(SELECT attnum FROM pg_attribute WHERE attrelid = 'app.learner_unit_states'::regclass "
            "AND attname = 'completed_count'))"
        )
    )

    assert "completion, never mastery" in comment
