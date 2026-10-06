"""
The importer of the mock members and its `--clean` (decision 66, plan 23).

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

from src import security
from src.cli import import_mock
from src.cli.import_mock import MockImportError
from src.config import Environment, Settings
from src.models import (
    Block,
    Bookmark,
    Comment,
    CommentStatus,
    FeedbackState,
    Follow,
    Insight,
    InsightFeedback,
    InsightPublication,
    MapCapturePoint,
    MapEntry,
    MapEntryGeneralisation,
    MapEntryRetiredId,
    MapEntrySponsorship,
    MapEntryStatus,
    Post,
    PostReaction,
    PostVisibility,
    QuranVerse,
    ReactionKind,
    Report,
    ReportReason,
    ReportTarget,
    Scan,
    User,
)
from src.models.consent import Consent, ConsentKind
from src.models.moderation import ModerationAction
from src.models.profile import Profile
from src.models.timeseries import EvidenceExposure
from src.models.world import WorldPlace, WorldReveal
from src.services import orphan_service
from tests import geo_dataset as world_data

AT = "2026-08-01T10:00:00Z"
LATER = "2026-08-02T11:30:00Z"
EXACT = (10.181534, 36.806512)
PUBLISH = "2026-08-03T09:00:00Z"
SPONSORED = "2026-09-20T09:00:00Z"


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
            {"placepix_id": 16, "scene": {"labels": ["sea"], "ar": "بحر"}, "insight": body()},
            {
                "placepix_id": 15,
                "scene": {"labels": ["sky"], "ar": "سماء"},
                "insight": body(hadith={"collection": "bukhari", "number": "8", "matched_on": "x"}),
            },
        ],
        "members": [
            member(
                "m1",
                "amal_tn",
                gender="woman",
                age_range="25_39",
                goals=["reflection", "curiosity"],
                knowledge_level="general",
                religious_background="muslim",
                theme="dark",
                reduced_motion="on",
                sound=True,
                public_full_name=True,
            ),
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
            insight(
                "i6",
                "m1",
                16,
                feedback={"helpful": False, "reasons": ["wrong_text"], "at": LATER},
            ),
            insight("i7", "m2", 16),
            insight("i8", "m1", 16),
            insight("i9", "m1", 16),
        ],
        "posts": [
            {
                "ref": "p1",
                "insight": "i1",
                "published_at": PUBLISH,
                "reflection": "تأمل قصير",
                "views": 137,
            },
            {"ref": "p2", "insight": "i5", "published_at": PUBLISH, "reflection": None},
            {"ref": "p3", "insight": "i4", "published_at": PUBLISH, "reflection": None},
            {
                "ref": "p5",
                "insight": "i7",
                "published_at": PUBLISH,
                "reflection": "بلا صورة",
                "visibility": "followers",
                "photo": False,
            },
            {"ref": "p4", "insight": "i2", "published_at": PUBLISH, "reflection": None},
        ],
        "map_entries": [
            {"insight": "i1", "published_at": PUBLISH},
            {"insight": "i4", "published_at": PUBLISH},
            {"insight": "i2", "published_at": PUBLISH},
            {
                "insight": "i6",
                "published_at": PUBLISH,
                "orphaned": True,
                "sponsor": {"member": "m2", "at": SPONSORED, "reflection": "كفالة طيبة"},
            },
            {
                "insight": "i7",
                "published_at": PUBLISH,
                "orphaned": True,
                "sponsor": {"member": "m2", "at": SPONSORED, "reflection": "لا تُقبل"},
            },
            {
                "insight": "i8",
                "published_at": PUBLISH,
                "orphaned": True,
                "sponsor": {"member": "m9", "at": SPONSORED},
            },
            {"insight": "i9", "published_at": PUBLISH, "orphaned": True},
        ],
        "follows": [
            {"from": "m1", "to": "m2", "at": AT},
            {"from": "m2", "to": "m1", "at": LATER},
            {"from": "m1", "to": "m1", "at": AT},
            {"from": "m1", "to": "m4", "at": AT},
            {"from": "m3", "to": "m2", "at": AT},
        ],
        "blocks": [{"from": "m2", "to": "m3", "at": LATER}, {"from": "m2", "to": "m9", "at": AT}],
        "bookmarks": [
            {"post": "p1", "member": "m2", "at": LATER},
            {"post": "p9", "member": "m3", "at": LATER},
        ],
        "reactions": [
            {"post": "p1", "member": "m2", "kind": "benefited", "at": LATER},
            {"post": "p1", "member": "m2", "kind": "benefited", "at": LATER},
            {"post": "p1", "member": "m3", "kind": "jazak", "at": LATER},
            {"post": "p9", "member": "m3", "kind": "benefited", "at": LATER},
            {"post": "p1", "member": "m2", "kind": "unknown_kind", "at": LATER},
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

    assert (report.members, report.insights, report.completions) == (3, 7, 6)
    assert report.posts == 3
    assert (report.entries, report.orphaned, report.sponsorships) == (5, 4, 1)
    assert report.follows == 2
    assert report.blocks == 1
    assert report.likes == 2
    assert report.bookmarks == 1
    assert report.comments == 2
    assert report.ignored_reactions == 1
    assert report.missing_evidence == ["i3"]
    assert report.skipped["insight whose image has no pipeline outcome"] == 1
    assert report.skipped["member with an unusable or taken handle"] == 1
    assert report.skipped["reply without its comment"] == 1
    assert report.skipped["comment without a text or a post"] == 1
    assert report.skipped["sponsorship refused by the app"] == 1
    assert len(report.lines()) >= 4

    amal = await db_session.scalar(select(User).where(User.handle == "amal_tn"))
    assert amal.email == "amal_tn@mock.tabsira.me"
    assert amal.is_active
    assert amal.public_full_name is True
    assert amal.email_verified_at is not None
    assert amal.created_at.isoformat() == "2026-08-01T10:00:00+00:00"
    profile = await db_session.get(Profile, amal.id)
    assert profile.photo_storage_consent is True
    assert profile.consent_version == settings.privacy_version
    assert profile.profile_completed_at.isoformat() == "2026-08-01T10:03:00+00:00"
    assert profile.questions_asked is True
    assert (profile.gender.value, profile.age_range.value) == ("woman", "25_39")
    assert profile.goals == ["reflection", "curiosity"]
    assert (profile.knowledge_level.value, profile.religious_background.value) == (
        "general",
        "muslim",
    )
    assert (profile.theme.value, profile.reduced_motion.value, profile.sound_enabled) == (
        "dark",
        "on",
        True,
    )
    assert profile.language == "ar"
    rows = (await db_session.scalars(select(Consent).where(Consent.user_id == amal.id))).all()
    assert sorted((c.kind.value, c.version, c.granted) for c in rows) == [
        ("photo_storage", settings.privacy_version, True),
        ("privacy", settings.privacy_version, True),
        ("public_country", settings.privacy_version, False),
        ("public_full_name", settings.privacy_version, True),
        ("terms", settings.terms_version, True),
    ]
    assert {c.created_at.isoformat() for c in rows} == {"2026-08-01T10:00:00+00:00"}
    bilal = await db_session.scalar(select(User).where(User.handle == "bilal_tn"))
    refused = await db_session.scalar(
        select(Consent.granted).where(
            Consent.user_id == bilal.id, Consent.kind == ConsentKind.PUBLIC_FULL_NAME
        )
    )
    assert refused is False

    post = await db_session.scalar(select(Post).where(Post.reflection == "تأمل قصير"))
    publication = await db_session.get(InsightPublication, post.publication_id)
    first = await db_session.get(Insight, publication.insight_id)
    assert first.engine == "pipeline"
    assert first.photo_key == "https://placepix.net/id/12/1080/1080"
    assert first.photo_public_key == first.photo_key
    assert first.completed_at.isoformat() == "2026-08-02T11:30:00+00:00"
    scan = await db_session.get(Scan, first.scan_id)
    assert scan.engine == "pipeline"

    assert post.published_at.isoformat() == "2026-08-03T09:00:00+00:00"
    assert post.visibility is PostVisibility.PUBLIC
    assert post.views_count == 137
    quiet = await db_session.scalar(select(Post).where(Post.reflection == "بلا صورة"))
    assert quiet.visibility is PostVisibility.FOLLOWERS
    # A file written before views were generated: none.
    assert quiet.views_count == 0
    assert (await db_session.get(InsightPublication, quiet.publication_id)).photo_ref is None

    entry = await db_session.scalar(
        select(MapEntry).where(MapEntry.user_id == amal.id, MapEntry.insight_id == first.id)
    )
    assert entry.published_at.isoformat() == "2026-08-03T09:00:00+00:00"
    assert entry.status is MapEntryStatus.PUBLISHED
    assert (entry.public_lat, entry.public_lng) != (EXACT[1], EXACT[0])
    point = await db_session.get(MapCapturePoint, entry.id)
    assert (point.latitude, point.longitude) == (EXACT[1], EXACT[0])
    assert await count(db_session, Follow) == 2
    assert await count(db_session, PostReaction) == 2
    assert await count(db_session, Comment) == 2
    assert await count(db_session, Bookmark) == 1
    assert await count(db_session, Block) == 1
    assert await count(db_session, Report) == 0
    assert await count(db_session, ModerationAction) == 0 + await count_widenings(db_session)


async def count_widenings(db: AsyncSession) -> int:
    """The daily job's own log row for each widened entry (`superseded_at_widening`)."""
    return await count(db, MapEntryRetiredId)


async def test_completions_write_the_world_and_the_exposures_as_a_save_does(
    db_session, settings, world
):
    await run(db_session, settings, document())
    amal = await db_session.scalar(select(User).where(User.handle == "amal_tn"))

    places = (
        await db_session.scalars(select(WorldPlace).where(WorldPlace.user_id == amal.id))
    ).all()
    reveals = (
        await db_session.scalars(select(WorldReveal).where(WorldReveal.user_id == amal.id))
    ).all()
    exposures = await db_session.scalar(
        select(func.count())
        .select_from(EvidenceExposure)
        .where(EvidenceExposure.user_id == amal.id)
    )
    assert len(places) == 1
    assert len(reveals) == 4
    assert exposures == 4
    done = (
        await db_session.scalars(
            select(Insight).where(Insight.user_id == amal.id, Insight.completed_at.is_not(None))
        )
    ).all()
    assert {i.place_id for i in done} == {places[0].id}
    assert min(r.learned_at for r in reveals).isoformat() == "2026-08-02T11:30:00+00:00"
    pending = await db_session.scalar(
        select(Insight).where(Insight.title == "ماء يجري", Insight.completed_at.is_(None))
    )
    assert pending is None or pending.place_id is None


async def test_the_feedback_is_kept_reviewed_so_the_admin_queue_stays_empty(
    db_session, settings, world
):
    await run(db_session, settings, document())

    row = await db_session.scalar(select(InsightFeedback))
    assert (row.helpful, row.reasons, row.state) == (False, ["wrong_text"], FeedbackState.REVIEWED)
    assert row.updated_at.isoformat() == "2026-08-02T11:30:00+00:00"
    assert await count(db_session, InsightFeedback) == 1


async def test_orphaned_entries_are_widened_by_the_jobs_function_and_half_are_sponsored(
    db_session, settings, world
):
    await run(db_session, settings, document())

    orphaned = (
        await db_session.scalars(select(MapEntry).where(MapEntry.widened_level.is_not(None)))
    ).all()
    assert len(orphaned) == 4
    assert await count(db_session, MapEntryGeneralisation) == 4
    assert await count(db_session, MapEntryRetiredId) == 4
    sponsored = await db_session.scalar(select(MapEntrySponsorship))
    entry = await db_session.get(MapEntry, sponsored.entry_id)
    assert entry.status is MapEntryStatus.PUBLISHED
    assert entry.last_active_at.isoformat() == "2026-09-20T09:00:00+00:00"
    assert sponsored.started_at.isoformat() == "2026-09-20T09:00:00+00:00"
    assert sponsored.reflection == "كفالة طيبة"
    assert sponsored.reflection_status is CommentStatus.PUBLISHED
    still = [e for e in orphaned if e.status is MapEntryStatus.ORPHANED]
    assert len(still) == 3
    # No public row says where the hidden point was.
    for row in orphaned:
        assert (row.public_lat, row.public_lng) != (EXACT[1], EXACT[0])


async def test_a_sponsorship_without_a_reflection_is_written_alone(db_session, settings, world):
    data = document()
    data["map_entries"] = [data["map_entries"][4]]
    data["map_entries"][0]["sponsor"] = {"member": "m3", "at": SPONSORED}
    data["map_entries"][0]["insight"] = "i6"

    report = await run(db_session, settings, data)

    assert report.sponsorships == 1
    assert (await db_session.scalar(select(MapEntrySponsorship))).reflection is None


async def test_an_entry_that_cannot_be_orphaned_stops_the_whole_import(
    db_session, settings, world, monkeypatch
):
    async def skipped(*_: Any) -> orphan_service.Marked:
        return orphan_service.Marked.SKIPPED

    monkeypatch.setattr(orphan_service, "mark_one", skipped)

    with pytest.raises(MockImportError, match="could not be orphaned"):
        await run(db_session, settings, document())


async def test_the_services_run_with_every_feature_on_whatever_the_host_switches_say(
    db_session, make_settings, world
):
    off = make_settings(disabled_features="atlas,world,photo_storage,social,treasure")

    report = await run(db_session, off, document())

    assert report.entries == 5
    assert await count(db_session, WorldReveal) > 0
    shown = await db_session.scalar(
        select(func.count()).select_from(Insight).where(Insight.photo_public_key.is_not(None))
    )
    assert shown > 0


async def test_every_member_signs_in_with_the_shared_password_and_nothing_asks_again(
    web, db_session, account_settings, world
):
    await run(db_session, account_settings, document())

    wrong = await web.post(
        "/auth/login", json={"email": "amal_tn@mock.tabsira.me", "password": "Tabsira"}
    )
    ok = await web.post(
        "/auth/login", json={"email": "Amal_TN@mock.tabsira.me", "password": "tabsira"}
    )
    me = (await web.get("/auth/me")).json()

    assert wrong.status_code == 401
    assert ok.status_code == 200
    assert me["legal_acceptance_required"] is False
    assert (await web.get("/profile")).status_code == 200
    assert (await web.get("/feed/latest")).status_code == 200
    assert (await web.get("/world")).status_code == 200


async def test_the_shared_password_is_hashed_with_the_configured_rounds(
    db_session, settings, world
):
    await run(db_session, settings, document())
    user = await db_session.scalar(select(User).where(User.handle == "amal_tn"))

    assert security.verify_password("tabsira", user.password_hash, settings.password_bcrypt_rounds)
    assert user.password_hash.startswith(f"$2b${settings.password_bcrypt_rounds:02d}$")


@pytest.mark.parametrize("value", ["under_13", "teen"])
def test_a_member_declared_under_13_or_unknown_is_a_wrong_shape(value):
    raw = json.dumps({"version": 1, "members": [member("m1", "amal_tn", age_range=value)]}).encode()
    with pytest.raises(MockImportError, match="wrong shape"):
        import_mock.parse(raw)


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

    assert (await import_mock.clean(db_session, settings)).accounts == 3
    assert (await import_mock.clean(db_session, settings)).accounts == 0
    assert await db_session.scalar(select(func.count()).select_from(User)) == 1
    for model in (Insight, Post, MapEntry, MapCapturePoint, Follow, PostReaction, Comment, Scan):
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
    # The one with a ruled-out hadith (bukhari 8) is kept but not published.
    assert sorted(i.hadith_number for i in kept) == ["1", "8"]
    posted = (await db_session.scalars(select(Post).where(Post.author_id == owner.id))).all()
    assert [p.reflection for p in posted] == ["بلا صورة"]


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
    template = make_settings(database_url=url + "tabsira_template")
    production = development.model_copy(update={"environment": Environment.PRODUCTION})
    check = import_mock.check_allowed

    with pytest.raises(MockImportError, match="--i-understand"):
        check(development, i_understand=False)
    with pytest.raises(MockImportError, match="test database"):
        check(test, i_understand=True)
    with pytest.raises(MockImportError, match="test database"):
        check(template, i_understand=True)
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
        def read(self, _limit: int) -> bytes:
            return b'{"version": 1}'

    class Client:
        def get_object(self, **values: str) -> dict[str, Any]:
            asked.append(values)
            return {"Body": Body(), "ContentLength": 14}

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


# ─── Privacy of --clean: what other members wrote is counted and never removed by surprise ───


async def a_real_member_around_the_mock_ones(db_session, settings, make_user):
    """A file imported, then a real member who comments, replies, reacts, follows and reports."""
    real = await make_user("real@example.com", verified=True)
    real.handle = "real_one"
    await db_session.flush()
    await run(db_session, settings, document())
    post = await db_session.scalar(select(Post).where(Post.reflection == "تأمل قصير"))
    mock_comment = await db_session.scalar(select(Comment).where(Comment.body == "بارك الله"))
    mock_user = await db_session.scalar(select(User).where(User.handle == "bilal_tn"))
    db_session.add_all(
        [
            Comment(
                post_id=post.id,
                author_id=real.id,
                parent_id=mock_comment.id,
                body="شكرا لك",
                status=CommentStatus.PUBLISHED,
            ),
            PostReaction(post_id=post.id, user_id=real.id, kind=ReactionKind.JAZAK),
            Bookmark(post_id=post.id, user_id=real.id),
            Follow(follower_id=real.id, followee_id=mock_user.id),
            Block(blocker_id=real.id, blocked_id=mock_user.id),
            Report(
                reporter_id=real.id,
                target_type=ReportTarget.POST,
                target_id=post.id,
                reason=ReportReason.OTHER,
            ),
        ]
    )
    await db_session.flush()
    return real


async def test_clean_refuses_when_other_members_rows_depend_on_mock_accounts(
    db_session, settings, world, make_user
):
    real = await a_real_member_around_the_mock_ones(db_session, settings, make_user)
    before = await count(db_session, User)

    with pytest.raises(MockImportError, match="--also-dependent-rows") as refused:
        await import_mock.clean(db_session, settings)

    for kind in ("comments or replies 1", "reactions 1", "bookmarks 1", "follows 1", "blocks 1"):
        assert kind in str(refused.value)
    assert "reports 1" in str(refused.value)
    assert await count(db_session, User) == before
    assert await db_session.get(User, real.id) is not None


async def test_clean_with_the_flag_removes_them_and_says_how_many(
    db_session, settings, world, make_user
):
    real = await a_real_member_around_the_mock_ones(db_session, settings, make_user)

    report = await import_mock.clean(db_session, settings, also_dependent_rows=True)

    assert report.accounts == 3
    assert report.dependents["comments or replies"] == 1
    assert await db_session.get(User, real.id) is not None
    for model in (Comment, PostReaction, Bookmark, Follow, Block, Report):
        assert await count(db_session, model) == 0


async def test_clean_counts_a_real_sponsor_of_a_mock_entry(db_session, settings, world, make_user):
    real = await make_user("sponsor@example.com", verified=True)
    await run(db_session, settings, document())
    entry = await db_session.scalar(select(MapEntry))
    db_session.add(MapEntrySponsorship(entry_id=entry.id, user_id=real.id))
    await db_session.flush()

    with pytest.raises(MockImportError, match="sponsorships 1"):
        await import_mock.clean(db_session, settings)


async def test_clean_survives_an_odd_photo_key_and_never_calls_the_storage(
    db_session, settings, world, monkeypatch
):
    await run(db_session, settings, document())
    for row in await db_session.scalars(select(Insight)):
        row.photo_key = "weird/../key"
        row.photo_public_key = "public/not-a-key"
    await db_session.flush()
    monkeypatch.setattr(import_mock, "_store", lambda _s: pytest.fail("storage used"))

    assert (await import_mock.clean(db_session, settings)).accounts == 3


async def test_an_old_domain_account_is_found_by_clean_and_by_the_next_import(
    db_session, settings, world
):
    await run(db_session, settings, document())
    for user in await db_session.scalars(select(User)):
        user.email = user.email.replace("mock.tabsira.me", "mock.tabsira.invalid")
    await db_session.flush()

    again = await run(db_session, settings, document())

    assert again.members == 0
    assert (await import_mock.clean(db_session, settings)).accounts == 3


def test_clean_flag_goes_with_clean_only():
    assert args("--clean", "--i-understand", "--also-dependent-rows").also_dependent_rows
    with pytest.raises(SystemExit):
        args("f.json", "--also-dependent-rows")


async def test_execute_says_what_other_members_rows_it_removed(
    db_session, settings, world, make_user, capsys
):
    await a_real_member_around_the_mock_ones(db_session, settings, make_user)
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    refused = await import_mock.execute(
        args("--clean", "--i-understand"), settings, factory, allow_test_database=True
    )
    assert refused == 1
    assert "--also-dependent-rows" in capsys.readouterr().err
    done = await import_mock.execute(
        args("--clean", "--i-understand", "--also-dependent-rows"),
        settings,
        factory,
        allow_test_database=True,
    )
    assert done == 0
    assert "removed 1 reactions of other members" in capsys.readouterr().out


# ─── The file's names and texts, the photo address and the size ───


async def test_a_scripture_look_alike_in_a_name_refuses_the_whole_file(db_session, settings, world):
    verse = await db_session.scalar(
        select(QuranVerse.text).where(QuranVerse.surah == 112, QuranVerse.ayah == 1)
    )
    data = document()
    data["members"][0]["display_name"] = verse

    with pytest.raises(MockImportError, match=r"member\.m1"):
        await run(db_session, settings, data)
    assert await count(db_session, User) == 0


@pytest.mark.parametrize(
    "text",
    [
        "زوروا https://example.com الآن",
        "راسلني على ali@example.com",
        "تابعني @someone",
        "اتصل على +216 20 123 456",
        "موقعي www.example.org",
        "x" * 900,
        "تأمل\x00",
        "قال تعالى: وما خلقت",
    ],
)
async def test_a_text_with_a_link_an_address_a_number_or_a_defect_refuses_the_file(
    db_session, settings, world, text
):
    data = document()
    data["comments"][0]["text"] = text

    with pytest.raises(MockImportError, match=r"comment\.c1"):
        await run(db_session, settings, data)
    assert await count(db_session, User) == 0


def test_text_problem_names_each_reason():
    check = import_mock.text_problem
    assert check("تأمل جميل", 50) is None
    assert check("   ", 50) == "empty"
    assert check("قال تعالى: وما خلقت", 50) == "reads like scripture"
    assert check("a\x00b", 50) == "control characters or too long"
    assert check("ab", 1) == "control characters or too long"
    assert check("see example.com", 50) == "a link, an address or a number"


@pytest.mark.parametrize("bad", [0, -5, 10**9 + 1])
def test_a_placepix_id_outside_the_bounds_makes_a_wrong_shape(bad):
    raw = json.dumps({"version": 1, "images": [{"placepix_id": bad}]}).encode()
    with pytest.raises(MockImportError, match="wrong shape"):
        import_mock.parse(raw)


def test_the_largest_id_gives_an_address_the_photo_rules_accept():
    from src.storage.base import is_mock_photo_address

    image = import_mock.ImageIn(placepix_id=10**9)
    assert is_mock_photo_address(import_mock.photo_address(image))


def test_a_big_local_file_is_refused_before_it_is_read(tmp_path, settings, monkeypatch):
    path = tmp_path / "big.json"
    path.write_bytes(b"{}")
    monkeypatch.setattr(import_mock, "MAX_FILE_BYTES", 1)

    with pytest.raises(MockImportError, match="larger than"):
        import_mock.read_source(str(path), settings)


@pytest.mark.parametrize("answer", [{"ContentLength": 99}, {}])
def test_a_big_s3_object_is_refused_by_its_length_or_by_the_capped_read(
    monkeypatch, settings, answer
):
    class Body:
        def read(self, limit: int) -> bytes:
            return b"x" * limit

    class Client:
        def get_object(self, **_: str) -> dict[str, Any]:
            return {"Body": Body(), **answer}

    monkeypatch.setattr("src.storage.s3.build_client", lambda _settings: Client())
    monkeypatch.setattr(import_mock, "MAX_FILE_BYTES", 10)

    with pytest.raises(MockImportError, match="larger than"):
        import_mock.read_source("s3://bucket/key", settings)


async def test_an_entry_that_resolves_to_another_country_is_left_out(
    db_session, settings, world, monkeypatch
):
    placed = import_mock.atlas_service.place

    async def across_the_border(db, *args, **kwargs):
        await placed(db, *args, **kwargs)
        for entry in (await db.scalars(select(MapEntry))).all():
            entry.country_iso2 = entry.country_iso2 or "TN"
        first = await db.scalar(select(MapEntry).order_by(MapEntry.id).limit(1))
        first.country_iso2 = "IL"

    monkeypatch.setattr(import_mock.atlas_service, "place", across_the_border)
    data = document()
    data["map_entries"] = [data["map_entries"][0]]

    report = await run(db_session, settings, data)

    assert report.entries == 0
    assert report.skipped["atlas entry resolved outside its member's country"] == 1
    assert await count(db_session, MapEntry) == 0


# ─── The declared country (decision 67) ───────────────────────────────────────


async def country_answers(db: AsyncSession) -> dict[str, tuple[str | None, bool, list[bool]]]:
    """Each mock member's declared country, its switch, and the `public_country` rows, by handle."""
    answers = {}
    for user in await db.scalars(select(User).where(User.email.endswith("@mock.tabsira.me"))):
        profile = await db.get(Profile, user.id)
        rows = await db.scalars(
            select(Consent.granted)
            .where(Consent.user_id == user.id, Consent.kind == ConsentKind.PUBLIC_COUNTRY)
            .order_by(Consent.created_at)
        )
        answers[user.handle] = (profile.country, profile.show_country, list(rows))
    return answers


def test_about_seven_members_in_ten_show_their_country_and_the_choice_is_stable():
    shown = sum(import_mock.shows_country(f"member_{n}") for n in range(1000))

    assert 650 <= shown <= 750
    assert import_mock.shows_country("Carim_tn") is import_mock.shows_country("carim_TN")
    assert [import_mock.shows_country(h) for h in ("amal_tn", "bilal_tn", "Carim_tn")] == [
        False,
        False,
        True,
    ]


async def test_every_member_declares_the_files_country_and_answers_the_switch_once(
    db_session, settings, world
):
    data = document()
    data["members"][1]["country"] = "tn"

    await run(db_session, settings, data)
    await run(db_session, settings, data)

    assert await country_answers(db_session) == {
        "amal_tn": ("TN", False, [False]),
        "bilal_tn": ("TN", False, [False]),
        "Carim_tn": ("TN", True, [True]),
    }
    carim = await db_session.scalar(select(User).where(User.handle == "Carim_tn"))
    row = await db_session.scalar(
        select(Consent).where(
            Consent.user_id == carim.id, Consent.kind == ConsentKind.PUBLIC_COUNTRY
        )
    )
    assert (row.version, row.created_at.isoformat()) == (
        settings.privacy_version,
        "2026-08-01T10:00:00+00:00",
    )


async def test_members_imported_before_the_country_get_it_on_the_next_run(
    db_session, settings, world
):
    data = document()
    for item in data["members"]:
        item["country"] = None
    await run(db_session, settings, data)
    assert {answer[0] for answer in (await country_answers(db_session)).values()} == {None}

    again = await run(db_session, settings, document())

    assert again.members == 0
    assert (await country_answers(db_session))["Carim_tn"] == ("TN", True, [True])


async def test_a_country_geonames_does_not_know_is_reported_and_left_empty(
    db_session, settings, world
):
    data = document()
    data["members"][0]["country"] = "XX"

    report = await run(db_session, settings, data)

    assert report.skipped["member country unknown to GeoNames"] == 1
    assert (await country_answers(db_session))["amal_tn"] == (None, False, [])
