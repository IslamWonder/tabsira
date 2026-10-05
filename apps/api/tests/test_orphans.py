"""
«كفالة بصيرة», the job (decision 60): quiet entries turn orphaned and their place widens for good.

The rules guarded here: the earlier cell lives in `map_entry_generalisations` and in no answer;
the widening is idempotent and is never undone by re-placing, publishing or sponsoring; the
author's name is gone from every public answer once the place is widened; a photo is not shown
again; a sponsored or recently active entry is left alone.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src import clock
from src.cli import mark_orphans
from src.features import FeatureFlag
from src.models import (
    GeoName,
    MapCapturePoint,
    MapEntry,
    MapEntryGeneralisation,
    MapEntrySponsorship,
    MapEntryStatus,
    WidenLevel,
)
from src.services import orphan_service
from src.storage.local import LocalStorage
from src.storage.photos import PhotoStore, build_photo_store
from tests import geo_dataset as world_data
from tests.helpers import switched
from tests.support_orphans import (
    BIGTOWN,
    HAMLET,
    HANDLE,
    OLD,
    entry_row,
    fresh,
    generalisations,
    run_job,
)
from tests.test_atlas import _insight, _place

# ─── What the job selects ───


async def test_a_quiet_unsponsored_entry_is_orphaned_and_the_others_are_left_alone(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    sponsor = await make_member("sponsor")
    quiet = await entry_row(db_session, author)
    recent = await entry_row(db_session, author, age_days=5)
    sponsored = await entry_row(db_session, author)
    db_session.add(MapEntrySponsorship(entry_id=sponsored.id, user_id=sponsor.user.id))
    draft = await entry_row(db_session, author, status=MapEntryStatus.DRAFT)
    removed = await entry_row(db_session, author, status=MapEntryStatus.REMOVED)
    await db_session.flush()

    report = await run_job(factory, db_session, make_settings)

    assert (report.marked, report.widened, report.failed) == (1, 1, 0)
    states = {
        name: (await fresh(db_session, entry)).status
        for name, entry in (
            ("quiet", quiet),
            ("recent", recent),
            ("sponsored", sponsored),
            ("draft", draft),
            ("removed", removed),
        )
    }
    assert states == {
        "quiet": MapEntryStatus.ORPHANED,
        "recent": MapEntryStatus.PUBLISHED,
        "sponsored": MapEntryStatus.PUBLISHED,
        "draft": MapEntryStatus.DRAFT,
        "removed": MapEntryStatus.REMOVED,
    }


async def test_the_job_takes_the_entries_in_a_shuffled_order_so_new_ids_keep_no_placing_order(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    entries = [await entry_row(db_session, author) for _ in range(5)]
    store = build_photo_store(make_settings())

    await orphan_service.mark_orphans(factory, 30, store, shuffle=lambda ids: ids.reverse())
    db_session.expunge_all()

    # Reversed here: the last placed got the first new id.
    new_ids = [(await fresh(db_session, entry)).id for entry in entries]
    assert new_ids == sorted(new_ids, reverse=True)
    for entry in entries:
        assert (await fresh(db_session, entry)).status is MapEntryStatus.ORPHANED


async def test_the_default_order_is_a_shuffle_of_the_system_generator():
    ids = list(range(50))

    orphan_service._SHUFFLE(ids)

    assert sorted(ids) == list(range(50)) and ids != list(range(50))


async def test_quiet_means_before_the_start_of_the_utc_day_the_days_ago(monkeypatch):
    monkeypatch.setattr(
        orphan_service.clock, "utcnow", lambda: datetime(2026, 10, 5, 15, 30, tzinfo=UTC)
    )

    assert orphan_service.cutoff_for(30) == datetime(2026, 9, 5, 0, 0, tzinfo=UTC)


# ─── How far the place widens ───


async def test_the_place_widens_to_the_region_and_the_earlier_cell_is_recorded(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    entry = await entry_row(
        db_session, author, place=world_data.MECCA_CITY, lat=21.4266, lng=39.8256
    )

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert widened.widened_level is WidenLevel.REGION
    assert (widened.public_lat, widened.public_lng) == (21.5, 40.5)
    assert widened.cell_m == orphan_service.LEVEL_CELL_M[WidenLevel.REGION]
    assert (widened.place_geoname_id, widened.place_label) == (
        world_data.MECCA_REGION,
        "مكة المكرّمة",
    )
    assert widened.admin_label is None and widened.country_iso2 == "SA"
    assert widened.status_reason is None
    [record] = await generalisations(db_session, entry)
    assert (record.previous_cell_m, record.previous_public_lat, record.previous_public_lng) == (
        1000,
        21.4266,
        39.8256,
    )
    assert (record.previous_place_label, record.new_level, record.new_label) == (
        "مكة المكرمة",
        WidenLevel.REGION,
        "مكة المكرّمة",
    )
    assert record.reason == "orphaned"


@pytest.mark.parametrize(
    ("place", "level", "point", "label"),
    [
        (BIGTOWN, WidenLevel.CITY, (35.0, 10.0), "Bigtown"),
        (HAMLET, WidenLevel.COUNTRY, (34.0, 9.0), "تونس"),
        (None, WidenLevel.GRID, None, None),
    ],
)
async def test_without_a_region_the_place_widens_to_a_city_a_country_or_a_large_cell(
    db_session, factory, make_member, make_settings, world, place, level, point, label
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author, place=place, lat=35.1, lng=10.1)

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert widened.widened_level is level
    assert widened.place_label == label
    if point is not None:
        assert widened.cell_m == orphan_service.LEVEL_CELL_M[level]
        assert (widened.public_lat, widened.public_lng) == point
    else:
        # A large cell around the public point: a point that is not the earlier one, no label.
        assert widened.cell_m in orphan_service.GRID_SIZES_M
        assert (widened.public_lat, widened.public_lng) != (35.1, 10.1)
        assert widened.place_geoname_id is None and widened.country_iso2 is None
    [record] = await generalisations(db_session, entry)
    assert (record.new_level, record.new_label) == (level, label)


@pytest.mark.parametrize(
    "point", [(36.8065, 10.1815), (36.8, 10.2), (36.7, 10.4)], ids=["near", "at the centre", "far"]
)
async def test_the_level_does_not_depend_on_how_far_the_hidden_point_is_from_the_area(
    db_session, factory, make_member, make_settings, world, point
):
    author = await make_member(HANDLE)
    # The level betrays the distance if it is chosen by it: here it is the same, region, whether
    # the earlier point is a few kilometres from the governorate's centre, on it, or farther.
    entry = await entry_row(db_session, author, lat=point[0], lng=point[1])

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert widened.widened_level is WidenLevel.REGION
    assert (widened.public_lat, widened.public_lng) == (36.8, 10.2)
    assert (widened.place_geoname_id, widened.place_label) == (
        world_data.TUNIS_GOVERNORATE,
        "ولاية تونس",
    )
    # Even a centre that is the earlier point is recorded: the cell, and the doubt, grew.
    assert widened.cell_m > 1000
    assert len(await generalisations(db_session, entry)) == 1


async def test_a_level_finer_than_the_cell_the_entry_already_has_is_passed_over(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    # The region (100 km) and the city (20 km) are both finer than the 200 km this entry has.
    entry = await entry_row(
        db_session, author, place=world_data.MECCA_CITY, lat=21.4266, lng=39.8256, cell_m=200_000
    )

    await run_job(factory, db_session, make_settings)

    assert (await fresh(db_session, entry)).widened_level is WidenLevel.COUNTRY


async def test_a_region_too_small_to_hide_in_is_passed_over(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    for geoname_id, name, code, lat, lng, population, admin in (
        (7000010, "Tinyregion", "ADM1", 33.0, 8.0, 5_000, "98"),
        (7000011, "Tinytown", "PPL", 33.5, 8.5, 3_000, "98"),
    ):
        db_session.add(
            GeoName(
                **world_data.place(
                    geoname_id,
                    name,
                    lat,
                    lng,
                    "A" if code == "ADM1" else "P",
                    code,
                    "TN",
                    admin,
                    population,
                ),
                location_geom=func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
            )
        )
    await db_session.flush()
    # The region's centre is 80 km away, far enough: it is its few people that make it no crowd.
    entry = await entry_row(db_session, author, place=7000011, lat=33.55, lng=8.55)

    await run_job(factory, db_session, make_settings)

    assert (await fresh(db_session, entry)).widened_level is WidenLevel.COUNTRY


@pytest.mark.parametrize(
    ("cell_m", "size"), [(50_000, 100_000), (400_000, 800_000), (30_000, 100_000)]
)
async def test_the_grid_is_the_first_fixed_size_at_least_twice_the_entry_s_cell(
    db_session, factory, make_member, make_settings, world, cell_m, size
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author, place=None, lat=35.1, lng=10.1, cell_m=cell_m)

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert (widened.widened_level, widened.cell_m) == (WidenLevel.GRID, size)


async def test_the_grid_of_an_ordinary_entry_is_the_finest_fixed_size(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author, place=None, lat=35.1, lng=10.1)

    await run_job(factory, db_session, make_settings)

    assert (await fresh(db_session, entry)).cell_m == 50_000


async def test_the_last_grid_size_is_taken_when_none_widens_enough(
    db_session, factory, make_member, make_settings, world, monkeypatch
):
    author = await make_member(HANDLE)
    monkeypatch.setattr(orphan_service, "GRID_SIZES_M", (50_000,))
    entry = await entry_row(db_session, author, place=None, lat=35.1, lng=10.1, cell_m=50_000)

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert (widened.widened_level, widened.cell_m) == (WidenLevel.GRID, 50_000)


@pytest.mark.parametrize("point", [(89.9, 0.0), (-89.9, 179.9), (0.0, 0.0)])
async def test_the_coarse_grid_stays_on_earth_at_the_poles_and_the_antimeridian(
    db_session, factory, make_member, make_settings, world, point
):
    author = await make_member(HANDLE)
    entry = await entry_row(
        db_session, author, place=None, lat=point[0], lng=point[1], cell_m=50_000
    )

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert widened.widened_level is WidenLevel.GRID and widened.cell_m > 50_000
    assert -90 <= (widened.public_lat or 0) <= 90 and -180 <= (widened.public_lng or 0) <= 180


async def test_a_place_with_no_country_or_no_centre_widens_to_a_large_cell(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    db_session.add(
        GeoName(
            **{
                **world_data.place(7000003, "Blank", 0.0, 0.0, "P", "PPL", "TN", "99", 90_000),
                "latitude": None,
                "longitude": None,
            }
        )
    )
    await db_session.flush()
    no_country = await entry_row(
        db_session, author, place=world_data.ZERO_POINT, lat=0.1, lng=0.1, country_iso2=None
    )
    no_centre = await entry_row(db_session, author, place=7000003, country_iso2=None)

    await run_job(factory, db_session, make_settings)

    for entry in (no_country, no_centre):
        assert (await fresh(db_session, entry)).widened_level is WidenLevel.GRID


async def test_a_place_that_is_not_in_geonames_widens_to_the_country_or_a_cell(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    lost = await entry_row(db_session, author, place=424242)
    nowhere = await entry_row(db_session, author, place=424242, country_iso2="XX")

    await run_job(factory, db_session, make_settings)

    assert (await fresh(db_session, lost)).widened_level is WidenLevel.COUNTRY
    assert (await fresh(db_session, nowhere)).widened_level is WidenLevel.GRID


async def test_the_job_never_reads_the_private_point(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    insight_id = await _insight(db_session, author)
    assert (await _place(author, insight_id)).status_code == 200
    assert (await author.http.post(f"/insights/{insight_id}/map/publish")).status_code == 200
    entry = await db_session.scalar(select(MapEntry))
    assert entry is not None
    entry.last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()
    point = await db_session.get(MapCapturePoint, entry.id)
    assert point is not None
    # A private point somewhere else entirely changes nothing about the widened place.
    point.latitude, point.longitude = -33.9, 18.4
    await db_session.flush()

    await run_job(factory, db_session, make_settings)

    widened = await fresh(db_session, entry)
    assert (widened.public_lat, widened.public_lng) == (36.8, 10.2)
    kept = await db_session.get(MapCapturePoint, widened.id)
    assert kept is not None and (kept.latitude, kept.longitude) == (-33.9, 18.4)


# ─── Idempotence and the second orphaning ───


async def test_a_second_run_changes_nothing(
    db_session, factory, make_member, make_settings, world, capsys
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author)
    settings = make_settings()

    assert await mark_orphans.execute(settings, factory) == 0
    first = await fresh(db_session, entry)
    snapshot = (first.status, first.public_lat, first.public_lng, first.cell_m, first.updated_at)
    [record] = await generalisations(db_session, entry)
    capsys.readouterr()

    assert await mark_orphans.execute(settings, factory) == 0

    again = await fresh(db_session, entry)
    assert (again.status, again.public_lat, again.public_lng, again.cell_m, again.updated_at) == (
        snapshot
    )
    assert [r.id for r in await generalisations(db_session, entry)] == [record.id]
    assert capsys.readouterr().out == "orphans: 0 entries orphaned, 0 places widened, 0 failed\n"


async def test_an_entry_orphaned_again_keeps_its_level_and_adds_no_record(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author)
    await run_job(factory, db_session, make_settings)
    widened = await fresh(db_session, entry)
    point = (widened.public_lat, widened.public_lng)
    # A sponsor looked after it, stopped, and nothing happened since.
    widened.status = MapEntryStatus.PUBLISHED
    widened.last_active_at = clock.utcnow() - timedelta(days=OLD)
    await db_session.flush()

    report = await run_job(factory, db_session, make_settings)

    again = await fresh(db_session, entry)
    assert (report.marked, report.widened) == (1, 0)
    assert again.status is MapEntryStatus.ORPHANED
    assert (again.widened_level, (again.public_lat, again.public_lng)) == (
        WidenLevel.REGION,
        point,
    )
    assert again.id == widened.id
    assert len(await generalisations(db_session, entry)) == 1


async def test_an_entry_that_woke_up_after_the_batch_was_chosen_is_left_alone(
    db_session, factory, make_member, make_settings, world
):
    author = await make_member(HANDLE)
    sponsor = await make_member("sponsor")
    awake = await entry_row(db_session, author, age_days=1)
    sponsored = await entry_row(db_session, author)
    db_session.add(MapEntrySponsorship(entry_id=sponsored.id, user_id=sponsor.user.id))
    gone = await entry_row(db_session, author, status=MapEntryStatus.WITHDRAWN)
    await db_session.flush()
    cutoff = orphan_service.cutoff_for(30)
    store = None

    async with factory() as db, db.begin():
        results = [
            await orphan_service.mark_one(db, entry.id, cutoff, store)  # type: ignore[arg-type]
            for entry in (awake, sponsored, gone)
        ]
        missing = await orphan_service.mark_one(db, 999, cutoff, store)  # type: ignore[arg-type]

    assert results == [orphan_service.Marked.SKIPPED] * 3
    assert missing is orphan_service.Marked.SKIPPED
    assert await db_session.scalar(select(func.count()).select_from(MapEntryGeneralisation)) == 0


# ─── The photo ───


async def test_the_photo_is_not_shown_again_once_the_place_is_widened(
    db_session, factory, make_member, make_settings, world, tmp_path
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author, with_photo=True)
    store = PhotoStore(
        LocalStorage(
            tmp_path,
            base_url="https://api.tabsira.test",
            signing_key=b"k" * 32,
            default_ttl_seconds=300,
        ),
        make_settings(),
    )

    report = await orphan_service.mark_orphans(factory, 30, store)

    assert report.widened == 1
    assert (await fresh(db_session, entry)).with_photo is False


async def test_a_photo_copy_the_store_would_not_delete_is_counted_as_a_failure(
    db_session, factory, make_member, make_settings, world, monkeypatch, capsys
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author, with_photo=True)

    async def refused(*args: object, **kwargs: object) -> bool:
        return False

    monkeypatch.setattr(orphan_service.photo_service, "sync_public_copy", refused)

    assert await mark_orphans.execute(make_settings(), factory) == 1

    # The place is widened all the same; the hourly reconcile deletes the copy.
    assert (await fresh(db_session, entry)).widened_level is not None
    assert capsys.readouterr().out == "orphans: 1 entries orphaned, 1 places widened, 1 failed\n"


# ─── The command ───


async def test_the_command_says_counts_only_and_exits_zero(
    db_session, factory, make_member, make_settings, world, capsys
):
    author = await make_member(HANDLE)
    await entry_row(db_session, author)
    await entry_row(db_session, author, place=None)

    assert await mark_orphans.execute(make_settings(), factory) == 0

    assert capsys.readouterr().out == "orphans: 2 entries orphaned, 2 places widened, 0 failed\n"


async def test_the_command_waits_for_the_thirty_days_the_setting_names(
    db_session, factory, make_member, make_settings, world, capsys
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author, age_days=45)

    await mark_orphans.execute(make_settings(orphan_after_days=60), factory)
    assert (await fresh(db_session, entry)).status is MapEntryStatus.PUBLISHED
    await mark_orphans.execute(make_settings(orphan_after_days=40), factory)
    assert (await fresh(db_session, entry)).status is MapEntryStatus.ORPHANED


async def test_an_entry_that_fails_is_counted_and_the_others_still_go(
    db_session, factory, make_member, make_settings, world, capsys, monkeypatch
):
    author = await make_member(HANDLE)
    broken = await entry_row(db_session, author)
    fine = await entry_row(db_session, author)
    real = orphan_service.mark_one

    async def flaky(db, entry_id, cutoff, store):
        if entry_id == broken.id:
            message = "the store is down"
            raise OSError(message)
        return await real(db, entry_id, cutoff, store)

    monkeypatch.setattr(orphan_service, "mark_one", flaky)

    assert await mark_orphans.execute(make_settings(), factory) == 1

    assert capsys.readouterr().out == "orphans: 1 entries orphaned, 1 places widened, 1 failed\n"
    assert (await fresh(db_session, fine)).status is MapEntryStatus.ORPHANED
    assert (await fresh(db_session, broken)).status is MapEntryStatus.PUBLISHED


async def test_nothing_is_done_while_sponsoring_is_switched_off(
    db_session, factory, make_member, make_settings, world, capsys
):
    author = await make_member(HANDLE)
    entry = await entry_row(db_session, author)
    off = switched(make_settings(), off=[FeatureFlag.ATLAS_SPONSORSHIP])
    parent_off = switched(make_settings(), off=[FeatureFlag.ATLAS])

    for settings in (off, parent_off):
        assert await mark_orphans.execute(settings, factory) == 0
        assert capsys.readouterr().out == "orphans: sponsoring is switched off; nothing done\n"
    assert (await fresh(db_session, entry)).status is MapEntryStatus.PUBLISHED


async def test_a_database_that_cannot_be_reached_exits_one_and_says_so(make_settings, capsys):
    from sqlalchemy.exc import OperationalError

    def broken():
        raise OperationalError("select 1", {}, OSError("down"))

    assert await mark_orphans.execute(make_settings(), broken) == 1
    assert "Cannot mark the orphaned entries (OperationalError)" in capsys.readouterr().err


async def test_without_a_factory_the_application_engine_is_used_and_closed(
    db_session, factory, make_settings, monkeypatch
):
    closed: list[bool] = []

    async def dispose() -> None:
        closed.append(True)

    monkeypatch.setattr(mark_orphans, "get_sessionmaker", lambda: factory)
    monkeypatch.setattr(mark_orphans, "dispose_engine", dispose)

    assert await mark_orphans.execute(make_settings()) == 0
    assert closed == [True]


def test_main_loads_the_settings_and_runs(monkeypatch, make_settings):
    seen: list[int] = []

    async def fake(settings, session_factory=None):
        seen.append(settings.orphan_after_days)
        return 0

    monkeypatch.setattr(mark_orphans, "execute", fake)
    monkeypatch.setattr(mark_orphans, "load_settings", make_settings)

    assert mark_orphans.main([]) == 0
    assert seen == [30]


def test_main_refuses_arguments_and_a_broken_configuration(monkeypatch, capsys):
    from src.config import ConfigError

    assert mark_orphans.main(["--now"]) == 2

    def refuse():
        message = "bad configuration"
        raise ConfigError(message)

    monkeypatch.setattr(mark_orphans, "load_settings", refuse)
    assert mark_orphans.main([]) == 1
    assert "bad configuration" in capsys.readouterr().err
