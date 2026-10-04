"""
The GeoNames import and update scripts, run for real on a tiny dump.

Nothing is downloaded: the cache directory is pre-filled with the dump files and
their `.done` markers, which is exactly what a finished download leaves. The
download function itself is tested against `file://` URLs. The scripts write to
the test database, so every test starts and ends with the geodata tables empty.
"""

from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text

from tests import geo_dataset as data
from tests.geo_dataset import place, write_dump, write_postal_codes

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED = REPO_ROOT / "scripts" / "seed-geonames.sh"
UPDATE = REPO_ROOT / "scripts" / "update-geonames.sh"
TABLES = (
    "geodata.geonames",
    "geodata.geonames_alternate_names",
    "geodata.geonames_hierarchy",
    "geodata.geonames_postal_codes",
    "geodata.geonames_country_info",
)
ALL_IDS = {item["geoname_id"] for item in data.PLACES}


async def truncate(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {', '.join(TABLES)}"))


@pytest.fixture(autouse=True)
async def empty_geodata(engine):
    await truncate(engine)
    yield
    await truncate(engine)


@pytest.fixture
def cache(tmp_path) -> Path:
    directory = tmp_path / "cache"
    write_dump(directory)
    return directory


def run(script: Path, *args: str, cache: Path, tmp_path: Path, **env: str):
    """Run a script against the test database and the given cache; capture what it says."""
    environment = {
        **os.environ,
        "GEONAMES_CACHE_DIR": str(cache),
        "GEONAMES_TMP_DIR": str(tmp_path),
        "SYNC_DATABASE_URL": "",
        **env,
    }
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


async def query(engine, sql: str, **params):
    async with engine.connect() as connection:
        return (await connection.execute(text(sql), params)).all()


async def scalar(engine, sql: str, **params):
    return (await query(engine, sql, **params))[0][0]


async def geoname_ids(engine, where: str = "true") -> set[int]:
    rows = await query(engine, f"SELECT geoname_id FROM geodata.geonames WHERE {where}")  # noqa: S608
    return {row[0] for row in rows}


@pytest.fixture
def seed(cache, tmp_path):
    def run_seed(*args: str, **env: str):
        return run(SEED, *args, cache=cache, tmp_path=tmp_path, **env)

    return run_seed


@pytest.fixture
def update(cache, tmp_path):
    def run_update(*args: str, **env: str):
        return run(UPDATE, *args, cache=cache, tmp_path=tmp_path, **env)

    return run_update


# ─── seed-geonames.sh ───────────────────────────────────────────────


async def test_the_seed_loads_places_names_hierarchy_and_countries(engine, seed):
    result = seed()

    assert result.returncode == 0, result.stdout + result.stderr
    # Places of class P and A only: the lake, the airport and the mountain are left out.
    assert await geoname_ids(engine) == ALL_IDS
    rows = await query(
        engine, "SELECT geoname_id, ar_name, is_active FROM geodata.geonames ORDER BY 1"
    )
    assert {row[0]: row[1] for row in rows} == {
        item["geoname_id"]: item["ar_name"] for item in data.PLACES
    }
    assert all(row[2] for row in rows)
    # Arabic and English names only, of the places that were kept.
    names = await query(
        engine,
        "SELECT alternate_name_id, iso_language, name_norm FROM geodata.geonames_alternate_names",
    )
    assert {row[0] for row in names} == {row[0] for row in data.NAMES if row[2] in {"ar", "en"}}
    assert {row[1] for row in names} == {"ar", "en"}
    assert {row[0]: row[2] for row in names}[17] == "mecca"
    assert await scalar(engine, "SELECT count(*) FROM geodata.geonames_hierarchy") == 4
    assert await scalar(engine, "SELECT count(*) FROM geodata.geonames_postal_codes") == 0
    assert "geonames_country_info" in result.stdout


async def test_the_seed_marks_the_flags_of_each_name(engine, seed):
    assert seed().returncode == 0

    flags = await query(
        engine,
        "SELECT alternate_name_id, is_preferred, is_short, is_colloquial, is_historic "
        "FROM geodata.geonames_alternate_names WHERE alternate_name_id IN (14, 15, 16, 21)",
    )
    assert {row[0]: row[1:] for row in flags} == {
        14: (False, True, False, False),
        15: (False, False, True, False),
        16: (True, False, False, False),
        21: (False, False, False, True),
    }


async def test_the_seed_fills_the_point_of_every_place_and_zero_is_a_coordinate(engine, seed):
    assert seed().returncode == 0

    points = await query(
        engine,
        "SELECT geoname_id, ST_X(location_geom), ST_Y(location_geom), ST_SRID(location_geom) "
        "FROM geodata.geonames",
    )
    expected = {item["geoname_id"]: item for item in data.PLACES}
    assert len(points) == len(expected)
    for geoname_id, longitude, latitude, srid in points:
        assert (longitude, latitude, srid) == (
            expected[geoname_id]["longitude"],
            expected[geoname_id]["latitude"],
            4326,
        )
    assert (0.0, 0.0) in {(row[1], row[2]) for row in points}


async def test_the_seed_loads_the_countries_with_their_flags(engine, seed):
    assert seed().returncode == 0

    rows = await query(
        engine,
        "SELECT iso2, country_name, flag_emoji, geoname_id, continent "
        "FROM geodata.geonames_country_info ORDER BY iso2",
    )
    assert rows == [
        ("FR", "France", "🇫🇷", None, "EU"),  # France itself is not in this dump
        ("SA", "Saudi Arabia", "🇸🇦", data.SAUDI_ARABIA, "AS"),
        ("TN", "Tunisia", "🇹🇳", data.TUNISIA, "AF"),
    ]


async def test_running_the_seed_again_replaces_what_it_loaded(engine, seed):
    assert seed().returncode == 0
    first = [
        await scalar(engine, f"SELECT count(*) FROM {table}")  # noqa: S608
        for table in TABLES
    ]

    assert seed().returncode == 0

    assert [
        await scalar(engine, f"SELECT count(*) FROM {table}")  # noqa: S608
        for table in TABLES
    ] == first


async def test_the_seed_with_a_limit_keeps_countries_and_regions_then_the_most_populated(
    engine, seed
):
    result = seed("--limit", "8")

    assert result.returncode == 0, result.stdout + result.stderr
    # Priority: the two countries and three regions, then populated places by population.
    # Places without a population, and other classes, are not candidates.
    assert await geoname_ids(engine) == {
        data.TUNISIA,
        data.SAUDI_ARABIA,
        data.TUNIS_GOVERNORATE,
        data.MECCA_REGION,
        data.RIYADH_REGION,
        data.OLD_TUNIS,
        data.RIYADH,
        data.PARIS,
    }
    # The names and the hierarchy follow the places that were kept.
    assert {
        row[0]
        for row in await query(engine, "SELECT geoname_id FROM geodata.geonames_alternate_names")
    } <= await geoname_ids(engine)


async def test_the_limit_can_be_written_with_an_equals_sign_and_cuts_the_regions_too(engine, seed):
    assert seed("--limit=3").returncode == 0

    assert await geoname_ids(engine) == {data.SAUDI_ARABIA, data.TUNISIA, data.RIYADH_REGION}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--limit", "abc"], "positive whole number"),
        (["--limit=0"], "positive whole number"),
        (["--limit", "-5"], "positive whole number"),
        (["--limit"], "needs a number"),
        (["--nonsense"], "unknown argument"),
    ],
)
async def test_the_seed_refuses_bad_arguments_before_touching_anything(
    engine, seed, arguments, message
):
    result = seed(*arguments)

    assert result.returncode != 0
    assert message in result.stdout + result.stderr
    assert await geoname_ids(engine) == set()


async def test_the_seed_explains_itself(seed):
    result = seed("--help")

    assert result.returncode == 0
    assert "Usage: scripts/seed-geonames.sh" in result.stdout
    assert "--postal-codes" in result.stdout


async def test_postal_codes_are_skipped_unless_asked_for(engine, seed, cache):
    write_postal_codes(
        cache,
        "TN\t1000\tTunis\tTunis\t36\t\t\t\t\t36.8\t10.18\t4\n"
        "TN\t1001\tTunis RP\tTunis\t36\t\t\t\t\t36.8\t10.18\t4\n",
    )

    assert seed().returncode == 0
    assert await scalar(engine, "SELECT count(*) FROM geodata.geonames_postal_codes") == 0

    result = seed("--postal-codes")

    assert result.returncode == 0, result.stdout + result.stderr
    assert await query(
        engine,
        "SELECT postal_code, place_name, latitude, accuracy FROM geodata.geonames_postal_codes "
        "ORDER BY postal_code",
    ) == [("1000", "Tunis", 36.8, 4), ("1001", "Tunis RP", 36.8, 4)]
    # A later run without the flag leaves them alone.
    assert seed().returncode == 0
    assert await scalar(engine, "SELECT count(*) FROM geodata.geonames_postal_codes") == 2


async def test_a_failed_load_changes_nothing(engine, seed, cache):
    assert seed().returncode == 0
    before = await geoname_ids(engine)
    # The postal file is loaded last, after the tables were emptied and refilled.
    write_postal_codes(cache, "TN\t1000\tTunis\tTunis\t36\t\t\t\t\t36.8\t10.18\tnot-a-number\n")

    result = seed("--postal-codes", "--limit", "4")

    assert result.returncode != 0
    # One transaction: the first import is still there, whole, and not the limited one.
    assert await geoname_ids(engine) == before
    assert await scalar(engine, "SELECT count(*) FROM geodata.geonames_alternate_names") == len(
        [row for row in data.NAMES if row[2] in {"ar", "en"}]
    )


async def test_a_dump_without_places_is_refused(engine, seed, cache):
    write_dump(cache, places=[])

    result = seed()

    assert result.returncode != 0
    assert "No places were extracted" in result.stdout + result.stderr


async def test_the_seed_needs_a_database_and_says_so(seed):
    result = seed(CI="true", DATABASE_URL="")

    assert result.returncode != 0
    assert "DATABASE_URL is not set" in result.stdout + result.stderr


async def test_in_ci_the_seed_writes_its_metrics(engine, seed, tmp_path):
    result = seed(CI="true", WORKSPACE=str(tmp_path / "workspace"))

    assert result.returncode == 0, result.stdout + result.stderr
    metrics = (tmp_path / "workspace" / ".ci_metrics" / "geonames.json").read_text()
    assert f'"rows":{len(data.PLACES)}' in metrics


# ─── update-geonames.sh ─────────────────────────────────────────────

KAIROUAN = 2473003


def changed_world():
    """The next month's dump: Sfax gone, Tunis grown, Kairouan new, a few names and links changed."""
    places = [dict(item) for item in data.PLACES if item["geoname_id"] != data.SFAX]
    for item in places:
        if item["geoname_id"] == data.TUNIS_CITY:
            item["population"] = 700000
    places.append(
        place(KAIROUAN, "Kairouan", 35.6781, 10.0963, "P", "PPLA", "TN", "33", 186653, "القيروان")
    )
    names = [row for row in data.NAMES if row[1] != data.SFAX and row[0] != 14]
    names.append((40, data.MECCA_CITY, "en", "Makkah Al-Mukarramah", False, False, False, False))
    names.append((41, KAIROUAN, "ar", "القيروان", True, False, False, False))
    hierarchy = [row for row in data.HIERARCHY if row[1] != data.HAMMAM_LIF]
    hierarchy.append((data.TUNISIA, data.TUNIS_CITY, "ADM"))
    return places, names, hierarchy


async def test_the_update_soft_deletes_what_vanished_and_changes_only_what_changed(
    engine, seed, update, cache
):
    assert seed().returncode == 0
    untouched = await scalar(
        engine,
        "SELECT xmin::text FROM geodata.geonames WHERE geoname_id = :id",
        id=data.HAMMAM_LIF,
    )
    tunis = await scalar(
        engine, "SELECT xmin::text FROM geodata.geonames WHERE geoname_id = :id", id=data.TUNIS_CITY
    )
    places, names, hierarchy = changed_world()
    write_dump(cache, places=places, names=names, hierarchy=hierarchy)

    result = update()

    assert result.returncode == 0, result.stdout + result.stderr
    # Sfax is soft-deleted, not removed; Kairouan is new; Tunis has its new population.
    assert await geoname_ids(engine, "is_active") == (ALL_IDS - {data.SFAX}) | {KAIROUAN}
    assert await geoname_ids(engine, "NOT is_active") == {data.SFAX}
    assert await geoname_ids(engine) == ALL_IDS | {KAIROUAN}
    assert (
        await scalar(
            engine,
            "SELECT population FROM geodata.geonames WHERE geoname_id = :id",
            id=data.TUNIS_CITY,
        )
        == 700000
    )
    kairouan = await query(
        engine,
        "SELECT ar_name, ST_Y(location_geom) FROM geodata.geonames WHERE geoname_id = :id",
        id=KAIROUAN,
    )
    assert kairouan == [("القيروان", 35.6781)]
    # A row that did not change is not rewritten; one that did is.
    assert untouched == await scalar(
        engine,
        "SELECT xmin::text FROM geodata.geonames WHERE geoname_id = :id",
        id=data.HAMMAM_LIF,
    )
    assert tunis != await scalar(
        engine, "SELECT xmin::text FROM geodata.geonames WHERE geoname_id = :id", id=data.TUNIS_CITY
    )
    # Names: Sfax's are gone with it, one of Mecca's was dropped and one added.
    name_ids = {
        row[0]
        for row in await query(
            engine, "SELECT alternate_name_id FROM geodata.geonames_alternate_names"
        )
    }
    assert name_ids == {row[0] for row in names if row[2] in {"ar", "en"}}
    assert 14 not in name_ids
    assert {40, 41} <= name_ids
    # Links: one went, one came.
    pairs = {
        (row[0], row[1])
        for row in await query(engine, "SELECT parent_id, child_id FROM geodata.geonames_hierarchy")
    }
    assert pairs == {(row[0], row[1]) for row in hierarchy}


async def test_a_place_that_comes_back_is_active_again_with_its_names(engine, seed, update, cache):
    assert seed().returncode == 0
    places, names, hierarchy = changed_world()
    write_dump(cache, places=places, names=names, hierarchy=hierarchy)
    assert update().returncode == 0
    assert await geoname_ids(engine, "NOT is_active") == {data.SFAX}

    write_dump(cache)
    result = update()

    assert result.returncode == 0, result.stdout + result.stderr
    assert await geoname_ids(engine, "NOT is_active") == {KAIROUAN}
    assert data.SFAX in await geoname_ids(engine, "is_active")
    assert (
        await scalar(
            engine, "SELECT ar_name FROM geodata.geonames WHERE geoname_id = :id", id=data.SFAX
        )
        == "صفاقس"
    )
    assert await scalar(
        engine,
        "SELECT count(*) FROM geodata.geonames_alternate_names WHERE geoname_id = :id",
        id=data.SFAX,
    ) == len([row for row in data.NAMES if row[1] == data.SFAX and row[2] in {"ar", "en"}])


async def test_the_update_also_works_on_empty_tables_like_a_first_import(engine, update):
    result = update()

    assert result.returncode == 0, result.stdout + result.stderr
    assert await geoname_ids(engine, "is_active") == ALL_IDS


async def test_the_update_refuses_a_dump_with_under_half_of_the_places(engine, seed, update, cache):
    assert seed().returncode == 0
    few = [item for item in data.PLACES if item["geoname_id"] in {data.TUNIS_CITY, data.MECCA_CITY}]
    write_dump(cache, places=few)

    result = update()

    assert result.returncode != 0
    assert "under half" in result.stdout + result.stderr
    assert await geoname_ids(engine, "is_active") == ALL_IDS

    forced = update("--force")

    assert forced.returncode == 0, forced.stdout + forced.stderr
    assert await geoname_ids(engine, "is_active") == {data.TUNIS_CITY, data.MECCA_CITY}
    assert len(await geoname_ids(engine, "NOT is_active")) == len(ALL_IDS) - 2


async def test_the_update_refuses_a_dump_without_places(engine, seed, update, cache):
    assert seed().returncode == 0
    write_dump(cache, places=[])

    result = update("--force")

    assert result.returncode != 0
    assert "holds no places" in result.stdout + result.stderr
    assert await geoname_ids(engine, "is_active") == ALL_IDS


async def test_the_update_explains_itself_and_refuses_unknown_arguments(update):
    helped = update("--help")
    refused = update("--now")

    assert helped.returncode == 0
    assert "Usage: scripts/update-geonames.sh" in helped.stdout
    assert refused.returncode != 0
    assert "unknown argument" in refused.stdout + refused.stderr


async def test_the_update_uses_a_cache_that_is_less_than_a_day_old_without_downloading(update):
    result = update()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Cache hit: allCountries.zip" in result.stdout


# ─── The download cache (geonames_fetch), against file:// URLs ──────


def fetch(url: str, destination: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """Call geonames_fetch the way the scripts do, with no network: the source is a local file."""
    script = (
        "set -Eeuo pipefail; source scripts/lib.sh; source scripts/geonames-common.sh; "
        'geonames_fetch "$1" "$2"'
    )
    return subprocess.run(
        ["bash", "-c", script, "fetch", url, str(destination)],
        cwd=REPO_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.fixture
def source(tmp_path) -> Path:
    """A zip of some size, standing in for a dump on the server."""
    path = tmp_path / "server" / "dump.zip"
    path.parent.mkdir()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zipped:
        zipped.writestr("dump.txt", "".join(f"{n}\tplace {n}\n" for n in range(2000)))
    return path


def test_a_download_is_saved_marked_done_and_leaves_no_partial_file(source, tmp_path):
    destination = tmp_path / "cache" / "dump.zip"

    result = fetch(source.as_uri(), destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert destination.read_bytes() == source.read_bytes()
    assert (tmp_path / "cache" / "dump.zip.done").exists()
    assert not (tmp_path / "cache" / "dump.zip.part").exists()
    assert "Downloading dump.zip" in result.stdout


def test_a_cached_file_is_used_without_going_back_to_the_server(source, tmp_path):
    destination = tmp_path / "cache" / "dump.zip"
    assert fetch(source.as_uri(), destination).returncode == 0
    source.unlink()

    result = fetch(source.as_uri(), destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Cache hit: dump.zip" in result.stdout


def test_a_file_without_its_done_marker_is_downloaded_again(source, tmp_path):
    destination = tmp_path / "cache" / "dump.zip"
    assert fetch(source.as_uri(), destination).returncode == 0
    (tmp_path / "cache" / "dump.zip.done").unlink()
    destination.write_bytes(b"half a file")

    result = fetch(source.as_uri(), destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no .done marker" in result.stdout
    assert destination.read_bytes() == source.read_bytes()


def test_a_cache_entry_older_than_the_limit_is_downloaded_again(source, tmp_path):
    destination = tmp_path / "cache" / "dump.zip"
    assert fetch(source.as_uri(), destination).returncode == 0
    three_days_ago = destination.stat().st_mtime - 3 * 86400
    os.utime(destination, (three_days_ago, three_days_ago))

    fresh_enough = fetch(source.as_uri(), destination, GEONAMES_MAX_AGE_DAYS="7")
    stale = fetch(source.as_uri(), destination, GEONAMES_MAX_AGE_DAYS="1")

    assert "Cache hit" in fresh_enough.stdout
    assert stale.returncode == 0, stale.stdout + stale.stderr
    assert "Cache stale: dump.zip is older than 1 day" in stale.stdout
    assert "Downloading dump.zip" in stale.stdout
    assert destination.stat().st_mtime > three_days_ago


def test_an_interrupted_download_is_resumed_where_it_stopped(source, tmp_path):
    destination = tmp_path / "cache" / "dump.zip"
    destination.parent.mkdir()
    whole = source.read_bytes()
    (tmp_path / "cache" / "dump.zip.part").write_bytes(whole[: len(whole) // 2])

    result = fetch(source.as_uri(), destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Resuming dump.zip from {len(whole) // 2} bytes" in result.stdout
    assert destination.read_bytes() == whole


def test_a_resumed_download_that_turns_out_corrupt_starts_again(source, tmp_path):
    destination = tmp_path / "cache" / "dump.zip"
    destination.parent.mkdir()
    # The server's file changed since the first bytes were fetched: they no longer match.
    (tmp_path / "cache" / "dump.zip.part").write_bytes(b"x" * 500)

    result = fetch(source.as_uri(), destination)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "incomplete or corrupt; starting it again" in result.stdout + result.stderr
    assert destination.read_bytes() == source.read_bytes()
    assert (tmp_path / "cache" / "dump.zip.done").exists()


def test_a_server_that_only_has_a_corrupt_file_ends_in_an_error_and_no_cache_entry(tmp_path):
    broken = tmp_path / "server" / "dump.zip"
    broken.parent.mkdir()
    broken.write_bytes(b"this is not a zip")
    destination = tmp_path / "cache" / "dump.zip"

    result = fetch(broken.as_uri(), destination)

    assert result.returncode != 0
    assert "still corrupt after a second download" in result.stdout + result.stderr
    assert not destination.exists()
    assert not (tmp_path / "cache" / "dump.zip.done").exists()


def test_a_failed_download_names_the_file_and_keeps_what_was_fetched_for_a_resume(tmp_path):
    destination = tmp_path / "cache" / "dump.zip"
    destination.parent.mkdir()
    (tmp_path / "cache" / "dump.zip.part").write_bytes(b"PK partial")

    result = fetch((tmp_path / "server" / "missing.zip").as_uri(), destination)

    assert result.returncode != 0
    assert "Download of dump.zip failed" in result.stdout + result.stderr
    assert not destination.exists()
    assert (tmp_path / "cache" / "dump.zip.part").read_bytes() == b"PK partial"


def test_a_text_file_is_complete_when_it_has_more_than_comments(tmp_path):
    good = tmp_path / "server" / "countryInfo.txt"
    good.parent.mkdir()
    good.write_text("# header\nTN\tTUN\n")
    comments_only = tmp_path / "server" / "empty.txt"
    comments_only.write_text("# header\n# nothing else\n")

    assert fetch(good.as_uri(), tmp_path / "cache" / "countryInfo.txt").returncode == 0
    refused = fetch(comments_only.as_uri(), tmp_path / "cache" / "empty.txt")

    assert refused.returncode != 0
    assert not (tmp_path / "cache" / "empty.txt").exists()
