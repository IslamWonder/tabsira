"""The tables of the scan workflow and the three time series."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.cli import timeseries_policy
from src.models import (
    ChatMessage,
    ChatStatus,
    EvidenceExposure,
    Guest,
    Insight,
    InsightOrigin,
    Scan,
    ScanSource,
    ScanStatus,
    Treasure,
    TreasureKind,
    WorldPlace,
    WorldRelation,
    timeseries,
)
from src.models.world import RelationReason

API_DIR = Path(__file__).resolve().parents[1]
GUEST = "a" * 64


def _migration() -> Any:
    path = API_DIR / "alembic" / "versions" / "20261004_190500_create_scan_time_series.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _guest(db: AsyncSession, key: str = GUEST) -> str:
    db.add(Guest(key=key))
    await db.flush()
    return key


def _scan(**values: Any) -> Scan:
    return Scan(
        **{
            "source": ScanSource.UPLOAD,
            "status": ScanStatus.QUEUED,
            "engine": "pipeline",
            **values,
        }
    )


def _insight(**values: Any) -> Insight:
    return Insight(
        **{
            "origin": InsightOrigin.SCAN,
            "engine": "pipeline",
            "title": "الحياة في قطرة",
            "glimpse": "لمحة",
            "relation": "direct",
            "explanation": [],
            "why": {"visible_clues": [], "concept": "الإحياء"},
            **values,
        }
    )


async def _refused(db: AsyncSession, row: Any, constraint: str) -> None:
    async with db.begin_nested():
        db.add(row)
        with pytest.raises(IntegrityError) as caught:
            await db.flush()
    assert constraint in str(caught.value)


async def test_a_scan_and_an_insight_have_exactly_one_owner(db_session, make_user):
    user = await make_user()
    key = await _guest(db_session)

    await _refused(db_session, _scan(), "ck_scans_one_owner")
    await _refused(db_session, _scan(user_id=user.id, guest_key=key), "ck_scans_one_owner")
    scan = _scan(guest_key=key)
    db_session.add(scan)
    await db_session.flush()

    await _refused(db_session, _insight(scan_id=scan.id), "ck_insights_one_owner")
    await _refused(db_session, _insight(guest_key=key), "ck_insights_scan_insight_has_a_scan")
    await _refused(
        db_session,
        _insight(guest_key=key, origin=InsightOrigin.TUTORIAL, tutorial_scene="rain"),
        "ck_insights_tutorial_insight_has_a_slug",
    )
    await _refused(
        db_session,
        _insight(guest_key=key, scan_id=scan.id, quran_surah=30),
        "ck_insights_quran_reference_whole",
    )
    insight = _insight(guest_key=key, scan_id=scan.id, quran_surah=30, quran_ayah=50)
    db_session.add(insight)
    await db_session.flush()

    assert scan.run == 1
    assert scan.sensitive is False
    assert scan.awaiting_ruling == []
    assert insight.completed_at is None


async def test_a_guest_key_is_the_64_hex_of_a_hash(db_session):
    await _refused(db_session, Guest(key="short"), "ck_guests_key_length")


async def test_a_tutorial_insight_is_kept_once_per_owner(db_session):
    key = await _guest(db_session)
    values = {
        "guest_key": key,
        "origin": InsightOrigin.TUTORIAL,
        "tutorial_scene": "rain-1.0",
        "tutorial_slug": "life-in-a-drop",
        "engine": "prepared",
    }
    db_session.add(_insight(**values))
    await db_session.flush()

    await _refused(db_session, _insight(**values), "uq_insights_guest_tutorial")


async def test_a_chat_message_is_counted_once_per_idempotency_key(db_session):
    key = await _guest(db_session)
    scan = _scan(guest_key=key)
    db_session.add(scan)
    await db_session.flush()
    insight = _insight(guest_key=key, scan_id=scan.id)
    db_session.add(insight)
    await db_session.flush()

    def message() -> ChatMessage:
        return ChatMessage(
            insight_id=insight.id,
            idempotency_key="k-1",
            status=ChatStatus.PENDING,
            question="لماذا؟",
        )

    db_session.add(message())
    await db_session.flush()

    await _refused(db_session, message(), "uq_insight_chat_messages_idempotency_key")
    await _refused(
        db_session,
        ChatMessage(
            insight_id=insight.id,
            idempotency_key="k-2",
            status=ChatStatus.ANSWERED,
            question="؟",
            level="e",
        ),
        "ck_insight_chat_messages_level",
    )


async def test_places_relations_and_treasures_keep_their_rules(db_session):
    key = await _guest(db_session)
    scan = _scan(guest_key=key)
    db_session.add(scan)
    await db_session.flush()
    first, second = (
        _insight(guest_key=key, scan_id=scan.id),
        _insight(guest_key=key, scan_id=scan.id),
    )
    rain = WorldPlace(guest_key=key, region_id="T01", regions_version="1.0")
    garden = WorldPlace(guest_key=key, region_id="T12", regions_version="1.0")
    db_session.add_all([first, second, rain, garden])
    await db_session.flush()

    await _refused(
        db_session,
        WorldPlace(guest_key=key, region_id="T01", regions_version="1.0"),
        "uq_world_places_guest_region",
    )
    low, high = sorted([rain.id, garden.id])
    await _refused(
        db_session,
        WorldRelation(
            place_a_id=high,
            place_b_id=low,
            reason=RelationReason.SAME_SCENE,
            insight_a_id=first.id,
            insight_b_id=second.id,
        ),
        "ck_world_relations_places_ordered",
    )
    await _refused(
        db_session,
        Treasure(
            insight_id=first.id,
            place_id=rain.id,
            kind=TreasureKind.DEEPER,
            learning_unit_id="T01_06",
            learning_path_version="tabsira-masar-1.0",
        ),
        "ck_treasures_has_evidence",
    )
    db_session.add(
        Treasure(
            insight_id=first.id,
            place_id=rain.id,
            kind=TreasureKind.ALTERNATIVE,
            quran_surah=6,
            quran_ayah=99,
            learning_unit_id="T01_03",
            learning_path_version="tabsira-masar-1.0",
        )
    )
    await db_session.flush()


async def test_deleting_a_guest_deletes_everything_it_owns(db_session):
    key = await _guest(db_session)
    scan = _scan(guest_key=key)
    db_session.add(scan)
    await db_session.flush()
    db_session.add(_insight(guest_key=key, scan_id=scan.id))
    db_session.add(WorldPlace(guest_key=key, region_id="T01", regions_version="1.0"))
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.guests WHERE key = :key"), {"key": key})

    for model in (Scan, Insight, WorldPlace):
        assert (await db_session.scalars(select(model))).all() == []


async def test_the_three_time_series_are_compressed_hypertables(db_session):
    rows = (
        await db_session.execute(
            text(
                "SELECT hypertable_name, compression_enabled "
                "FROM timescaledb_information.hypertables WHERE hypertable_schema = 'app'"
            )
        )
    ).all()
    jobs = (
        await db_session.execute(
            text(
                "SELECT hypertable_name, proc_name FROM timescaledb_information.jobs "
                "WHERE hypertable_schema = 'app'"
            )
        )
    ).all()

    assert {row.hypertable_name for row in rows if row.compression_enabled} >= {
        "scan_events",
        "ai_calls",
        "evidence_exposures",
    }
    for table in ("scan_events", "ai_calls", "evidence_exposures"):
        assert {job.proc_name for job in jobs if job.hypertable_name == table} == {
            "policy_compression",
            "policy_retention",
        }
    db_session.add(EvidenceExposure(guest_key=GUEST, kind="completed", quran_surah=30))
    await db_session.flush()


def test_the_migration_writes_the_statements_the_models_write():
    migration = _migration()

    assert migration.HYPERTABLES == timeseries.HYPERTABLES
    for table in timeseries.HYPERTABLES:
        assert migration.hypertable_statements(table) == timeseries.hypertable_statements(table)
        assert migration.policy_statements(table, 9, 2) == timeseries.policy_statements(table, 9, 2)


# ─── src.cli.timeseries_policy ─────────────────────────────────────


@pytest.fixture
async def maker(engine):
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
    finally:
        await transaction.rollback()
        await connection.close()


async def test_the_command_replaces_every_policy_from_the_settings(maker, make_settings, capsys):
    settings = make_settings(ai_calls_retention_days=90, ai_calls_compress_after_days=3)

    assert await timeseries_policy.apply(maker, settings) == 0

    async with maker() as session:
        config = (
            await session.execute(
                text(
                    "SELECT config FROM timescaledb_information.jobs "
                    "WHERE hypertable_name = 'ai_calls' AND proc_name = 'policy_retention'"
                )
            )
        ).scalar_one()
    assert config["drop_after"] == "90 days"
    assert "app.ai_calls: compressed after 3 days, kept 90 days" in capsys.readouterr().out


class _BrokenSession:
    async def __aenter__(self) -> _BrokenSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    def begin(self) -> _BrokenSession:
        return self

    async def execute(self, _statement: object) -> None:
        message = "refused"
        raise SQLAlchemyError(message)


async def test_the_command_reports_a_refusal(make_settings, capsys):
    code = await timeseries_policy.apply(_BrokenSession, make_settings())  # type: ignore[arg-type]

    assert code == 1
    assert "The policies were not changed: SQLAlchemyError" in capsys.readouterr().err


def test_main_applies_the_settings_and_closes_the_engine(monkeypatch):
    applied: list[object] = []
    disposed: list[bool] = []

    async def fake_apply(maker: object, settings: object) -> int:
        applied.append(settings)
        return 0

    async def dispose() -> None:
        disposed.append(True)

    monkeypatch.setattr(timeseries_policy, "apply", fake_apply)
    monkeypatch.setattr(timeseries_policy, "dispose_engine", dispose)

    assert timeseries_policy.main([]) == 0
    assert len(applied) == 1
    assert disposed == [True]
