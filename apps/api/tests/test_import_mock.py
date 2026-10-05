"""
The importer of the mock members and its `--clean` (decision 63, plan 22).

A small version-1 file goes through the real services on the test database: members, insights
with their placepix photo addresses, posts, atlas entries, follows, likes and comments. The
photo storage handed to the services refuses every call, so no placepix key ever reaches it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.cli import import_mock
from src.cli.import_mock import MockImportError
from src.config import Environment, Settings
from src.models import (
    Comment,
    Follow,
    Insight,
    MapCapturePoint,
    MapEntry,
    Post,
    PostLike,
    QuranVerse,
    Scan,
    User,
)
from src.models.consent import Consent
from src.models.profile import Profile
from tests import geo_dataset as world_data

AT = "2026-08-01T10:00:00Z"
LATER = "2026-08-02T11:30:00Z"
EXACT = (10.181534, 36.806512)
PUBLISH = "2026-08-03T09:00:00Z"


def body(**values: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "title": "ماء يجري",
        "glimpse": "الماء يعلّمنا الجريان",
        "concept": "الماء",
        "clues": ["ماء في الصورة"],
        "quran": {"surah": 112, "ayah": 1, "matched_on": "الإخلاص"},
        "hadith": {"collection": "bukhari", "number": "1", "matched_on": "النية"},
        "explanation": [{"section": "seen", "text": "نرى ماء يجري بهدوء."}],
        "small_step": {"text": "اشرب ماءً بهدوء", "kind": "reflection"},
    }
    return document | values


def member(ref: str, handle: str, **values: Any) -> dict[str, Any]:
    return {
        "ref": ref,
        "handle": handle,
        "display_name": "عبد الله",
        "country": "TN",
        "city_geoname_id": 2464470,
        "joined_at": AT,
    } | values


def insight(ref: str, owner: str, image: int, **values: Any) -> dict[str, Any]:
    return {
        "ref": ref,
        "member": owner,
        "image": image,
        "created_at": AT,
        "completed_at": LATER,
        "point": list(EXACT),
    } | values


def document() -> dict[str, Any]:
    return {
        "version": 1,
        "seed": 42,
        "images": [
            {"placepix_id": 12, "scene": {"labels": ["water"], "ar": "ماء"}, "insight": body()},
            {"placepix_id": 13, "scene": {"labels": ["cat"], "ar": "قطة"}, "insight": None},
            {
                "placepix_id": 14,
                "scene": {"labels": ["tree"], "ar": "شجرة"},
                "insight": body(
                    hadith={"collection": "bukhari", "number": "9999", "matched_on": "x"}
                ),
            },
            {
                "placepix_id": 15,
                "scene": {"labels": ["sky"], "ar": "سماء"},
                "insight": body(hadith={"collection": "bukhari", "number": "8", "matched_on": "x"}),
            },
        ],
        "members": [
            member("m1", "amal_tn"),
            member("m2", "bilal_tn"),
            member("m3", "Carim_tn"),
            member("m4", "1bad"),
        ],
        "insights": [
            insight("i1", "m1", 12),
            insight("i2", "m1", 13),
            insight("i3", "m2", 14),
            insight("i4", "m2", 15),
            insight("i5", "m3", 12, completed_at=None),
        ],
        "posts": [
            {"ref": "p1", "insight": "i1", "published_at": PUBLISH, "reflection": "تأمل قصير"},
            {"ref": "p2", "insight": "i5", "published_at": PUBLISH, "reflection": None},
            {"ref": "p3", "insight": "i4", "published_at": PUBLISH, "reflection": None},
            {"ref": "p4", "insight": "i2", "published_at": PUBLISH, "reflection": None},
        ],
        "map_entries": [
            {"insight": "i1", "published_at": PUBLISH},
            {"insight": "i4", "published_at": PUBLISH},
            {"insight": "i2", "published_at": PUBLISH},
        ],
        "follows": [
            {"from": "m1", "to": "m2", "at": AT},
            {"from": "m2", "to": "m1", "at": LATER},
            {"from": "m1", "to": "m1", "at": AT},
            {"from": "m1", "to": "m4", "at": AT},
        ],
        "reactions": [
            {"post": "p1", "member": "m2", "kind": "benefited", "at": LATER},
            {"post": "p1", "member": "m2", "kind": "benefited", "at": LATER},
            {"post": "p1", "member": "m3", "kind": "jazak", "at": LATER},
            {"post": "p9", "member": "m3", "kind": "benefited", "at": LATER},
        ],
        "comments": [
            {
                "ref": "c1",
                "post": "p1",
                "member": "m2",
                "parent": None,
                "text": "بارك الله",
                "at": LATER,
            },
            {
                "ref": "c2",
                "post": "p1",
                "member": "m3",
                "parent": "c1",
                "text": "آمين",
                "at": LATER,
            },
            {"ref": "c3", "post": "p1", "member": "m3", "parent": None, "text": None, "at": LATER},
            {"ref": "c4", "post": "p1", "member": "m3", "parent": "c9", "text": "رد", "at": LATER},
        ],
    }


@pytest.fixture
async def world(db_session: AsyncSession, scripture: None) -> None:
    await world_data.load_world(db_session)


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings()


async def count(db: AsyncSession, model: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def run(
    db: AsyncSession, settings: Settings, data: dict[str, Any]
) -> import_mock.ImportReport:
    return await import_mock.import_file(db, settings, import_mock.parse(json.dumps(data).encode()))


async def test_the_file_is_written_through_the_services(db_session, settings, world):
    report = await run(db_session, settings, document())

    assert (report.members, report.insights, report.completions) == (3, 3, 2)
    assert report.posts == 2
    assert report.entries == 1
    assert report.follows == 2
    assert report.likes == 1
    assert report.comments == 2
    assert report.ignored_reactions == 1
    assert report.missing_evidence == ["i3"]
    assert report.skipped["insight whose image has no pipeline outcome"] == 1
    assert report.skipped["member with an unusable or taken handle"] == 1
    assert report.skipped["reply without its comment"] == 1
    assert report.skipped["comment without a text or a post"] == 1
    assert len(report.lines()) >= 4

    amal = await db_session.scalar(select(User).where(User.handle == "amal_tn"))
    assert amal.email == "amal_tn@mock.tabsira.invalid"
    assert amal.password_hash is None
    assert amal.email_verified_at is not None
    assert amal.created_at.isoformat() == "2026-08-01T10:00:00+00:00"
    profile = await db_session.get(Profile, amal.id)
    assert profile.photo_storage_consent is True
    kinds = sorted(
        c.kind.value
        for c in await db_session.scalars(select(Consent).where(Consent.user_id == amal.id))
    )
    assert kinds == ["photo_storage", "privacy", "terms"]

    first = await db_session.scalar(select(Insight).where(Insight.user_id == amal.id))
    assert first.engine == "pipeline"
    assert first.photo_key == "https://placepix.net/id/12/1080/1080"
    assert first.photo_public_key == first.photo_key
    assert first.completed_at.isoformat() == "2026-08-02T11:30:00+00:00"
    scan = await db_session.get(Scan, first.scan_id)
    assert scan.engine == "pipeline"

    post = await db_session.scalar(select(Post).where(Post.author_id == amal.id))
    assert post.published_at.isoformat() == "2026-08-03T09:00:00+00:00"
    assert post.reflection == "تأمل قصير"

    entry = await db_session.scalar(select(MapEntry).where(MapEntry.user_id == amal.id))
    assert entry.published_at.isoformat() == "2026-08-03T09:00:00+00:00"
    assert (entry.public_lat, entry.public_lng) != (EXACT[1], EXACT[0])
    point = await db_session.get(MapCapturePoint, entry.id)
    assert (point.latitude, point.longitude) == (EXACT[1], EXACT[0])
    assert await count(db_session, Follow) == 2
    assert await count(db_session, PostLike) == 1
    assert await count(db_session, Comment) == 2


async def test_a_second_run_imports_nothing_and_clean_removes_only_mock_rows(
    db_session, settings, world, make_user
):
    real = await make_user("real@example.com", verified=True)
    real.handle = "real_one"
    await db_session.flush()
    await run(db_session, settings, document())
    before = {m: await count(db_session, m) for m in (User, Insight, Post, MapEntry, Follow)}

    again = await run(db_session, settings, document())

    assert (again.members, again.insights, again.posts, again.entries, again.follows) == (
        0,
        0,
        0,
        0,
        0,
    )
    assert {m: await count(db_session, m) for m in before} == before

    assert await import_mock.clean(db_session, settings) == 3
    assert await import_mock.clean(db_session, settings) == 0
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    for model in (Insight, Post, MapEntry, MapCapturePoint, Follow, PostLike, Comment, Scan):
        assert await count(db_session, model) == 0
    assert await db_session.get(User, real.id) is not None


async def test_a_taken_handle_is_skipped(db_session, settings, world, make_user):
    taken = await make_user("other@example.com", verified=True)
    taken.handle = "AMAL_TN"
    await db_session.flush()

    report = await run(db_session, settings, document())

    assert report.members == 2


async def test_an_insight_whose_evidence_is_missing_is_skipped_never_replaced(
    db_session, settings, world
):
    report = await run(db_session, settings, document())

    assert report.missing_evidence == ["i3"]
    owner = await db_session.scalar(select(User).where(User.handle == "bilal_tn"))
    kept = (await db_session.scalars(select(Insight).where(Insight.user_id == owner.id))).all()
    # Only the one with a ruled-out hadith (bukhari 8) is kept, and it is not published.
    assert [i.hadith_number for i in kept] == ["8"]
    assert await db_session.scalar(select(Post).where(Post.author_id == owner.id)) is None


async def test_a_text_that_is_scripture_refuses_the_whole_file(db_session, settings, world):
    verse = await db_session.scalar(
        select(QuranVerse.text).where(QuranVerse.surah == 112, QuranVerse.ayah == 1)
    )
    data = document()
    data["posts"][0]["reflection"] = verse

    with pytest.raises(MockImportError, match=r"post\.p1"):
        await run(db_session, settings, data)
    assert await count(db_session, User) == 0


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        json.dumps({"version": 2}).encode(),
        json.dumps({"version": 1, "members": [{}]}).encode(),
    ],
)
def test_a_file_of_another_version_or_shape_is_refused(raw):
    with pytest.raises(MockImportError):
        import_mock.parse(raw)


def test_the_empty_file_has_nothing_to_check():
    assert import_mock.parse(b'{"version": 1}').members == []


async def test_an_empty_file_writes_nothing(db_session, settings, world):
    report = await run(db_session, settings, {"version": 1})

    assert report.members == 0


def test_the_storage_given_to_the_services_refuses_every_call(settings):
    store = import_mock._store(settings)
    with pytest.raises(AssertionError):
        store.storage.put("x", b"")


# ─── What may run, and where the file comes from ───


def test_the_command_refuses_without_understanding_the_test_database_and_production(
    make_settings,
):
    url = "postgresql+asyncpg://u:p@127.0.0.1:5432/"
    development = make_settings(database_url=url + "tabsira")
    test = make_settings(database_url=url + "tabsira_test")
    production = development.model_copy(update={"environment": Environment.PRODUCTION})
    check = import_mock.check_allowed

    with pytest.raises(MockImportError, match="--i-understand"):
        check(development, i_understand=False)
    with pytest.raises(MockImportError, match="test database"):
        check(test, i_understand=True)
    with pytest.raises(MockImportError, match="--allow-production"):
        check(production, i_understand=True)
    check(development, i_understand=True)
    check(test, i_understand=True, allow_test_database=True)
    check(production, i_understand=True, allow_production=True)


def test_a_local_file_is_read_and_a_missing_one_is_reported(tmp_path: Path, settings):
    path = tmp_path / "mock.json"
    path.write_bytes(b'{"version": 1}')

    assert import_mock.read_source(str(path), settings) == b'{"version": 1}'
    with pytest.raises(MockImportError, match="cannot read"):
        import_mock.read_source(str(tmp_path / "none.json"), settings)


def test_an_s3_file_is_read_with_the_project_s3_client(monkeypatch, settings):
    asked: list[dict[str, str]] = []

    class Body:
        def read(self) -> bytes:
            return b'{"version": 1}'

    class Client:
        def get_object(self, **values: str) -> dict[str, Body]:
            asked.append(values)
            return {"Body": Body()}

    monkeypatch.setattr("src.storage.s3.build_client", lambda _settings: Client())

    assert import_mock.read_source("s3://bucket/mock/v1.json", settings) == b'{"version": 1}'
    assert asked == [{"Bucket": "bucket", "Key": "mock/v1.json"}]


def test_an_s3_failure_is_reported_without_the_address_of_the_bucket_keys(monkeypatch, settings):
    class Client:
        def get_object(self, **_: str) -> None:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")

    monkeypatch.setattr("src.storage.s3.build_client", lambda _settings: Client())

    with pytest.raises(MockImportError, match="ClientError"):
        import_mock.read_source("s3://bucket/key", settings)


# ─── The command ───


def args(*argv: str) -> Any:
    return import_mock._arguments(list(argv))


def test_the_arguments_need_a_file_or_clean_alone():
    assert args("--clean", "--i-understand").clean is True
    assert args("f.json", "--i-understand", "--allow-production").allow_production is True
    for bad in ([], ["f.json", "--clean"]):
        with pytest.raises(SystemExit):
            args(*bad)


async def test_execute_imports_then_cleans_and_reports(
    db_session, settings, world, tmp_path, capsys
):
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    path = tmp_path / "mock.json"
    path.write_text(json.dumps(document()), encoding="utf-8")

    refused = await import_mock.execute(
        args(str(path)), settings, factory, allow_test_database=True
    )
    assert refused == 1
    done = await import_mock.execute(
        args(str(path), "--i-understand"), settings, factory, allow_test_database=True
    )
    assert done == 0
    assert "members 3" in capsys.readouterr().out
    cleaned = await import_mock.execute(
        args("--clean", "--i-understand"), settings, factory, allow_test_database=True
    )
    assert cleaned == 0
    assert "removed 3 mock accounts" in capsys.readouterr().out


async def test_execute_reports_a_bad_file_and_an_unreachable_database(
    db_session, settings, tmp_path, capsys
):
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    path = tmp_path / "mock.json"
    path.write_text("{}", encoding="utf-8")
    bad = await import_mock.execute(
        args(str(path), "--i-understand"), settings, factory, allow_test_database=True
    )
    assert bad == 1
    assert "unsupported file version" in capsys.readouterr().err

    class Down:
        def __call__(self) -> Any:
            raise OperationalError("select 1", {}, OSError("down"))

    path.write_text('{"version": 1}', encoding="utf-8")
    down = await import_mock.execute(
        args(str(path), "--i-understand"),
        settings,
        Down(),
        allow_test_database=True,  # type: ignore[arg-type]
    )
    assert down == 1
    assert "Cannot reach the database" in capsys.readouterr().err


def test_main_builds_the_settings_and_runs(monkeypatch, settings):
    async def execute(parsed: Any, given: Settings) -> int:
        assert given is settings
        return 7

    monkeypatch.setattr(import_mock, "load_settings", lambda: settings)
    monkeypatch.setattr(import_mock, "execute", execute)

    assert import_mock.main(["--clean", "--i-understand"]) == 7


def test_main_reports_a_broken_configuration(monkeypatch, capsys):
    def broken() -> Settings:
        raise import_mock.ConfigError("no database")

    monkeypatch.setattr(import_mock, "load_settings", broken)

    assert import_mock.main(["--clean", "--i-understand"]) == 1
    assert "no database" in capsys.readouterr().err


async def test_an_insight_with_a_verse_alone_and_no_step_is_kept(db_session, settings, world):
    data = {
        "version": 1,
        "images": [
            {
                "placepix_id": 20,
                "scene": {"ar": "نهر"},
                "insight": body(hadith=None, small_step=None),
            }
        ],
        "members": [member("m1", "amal_tn")],
        "insights": [insight("i1", "m1", 20)],
    }

    report = await run(db_session, settings, data)

    assert (report.members, report.insights) == (1, 1)
    kept = await db_session.scalar(select(Insight))
    assert (kept.hadith_collection, kept.small_step) == (None, None)


async def test_without_a_session_factory_the_engine_is_used_and_closed(
    db_session, settings, monkeypatch
):
    closed: list[bool] = []

    async def dispose() -> None:
        closed.append(True)

    monkeypatch.setattr(
        import_mock,
        "get_sessionmaker",
        lambda: async_sessionmaker(bind=db_session.bind, expire_on_commit=False),
    )
    monkeypatch.setattr(import_mock, "dispose_engine", dispose)

    code = await import_mock.execute(
        args("--clean", "--i-understand"), settings, allow_test_database=True
    )

    assert code == 0
    assert closed == [True]


def test_the_photo_address_is_the_files_own_placepix_address() -> None:
    image = import_mock.ImageIn(placepix_id=6, url="https://placepix.net/id/6/640/480")
    assert import_mock.photo_address(image) == "https://placepix.net/id/6/640/480"


@pytest.mark.parametrize("url", [None, "https://placepix.net.evil.com/id/6/640/480"])
def test_an_image_without_a_placepix_address_takes_the_default_size(url: str | None) -> None:
    image = import_mock.ImageIn(placepix_id=6, url=url)
    assert import_mock.photo_address(image) == "https://placepix.net/id/6/1080/1080"
