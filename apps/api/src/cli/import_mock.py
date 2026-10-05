"""
Import the mock members that start the platform, or remove them (decision 63, plan 22).

    uv run python -m src.cli.import_mock <file-or-s3://bucket/key> --i-understand
    uv run python -m src.cli.import_mock --clean --i-understand

The file (`tabsira-mock-v1.json`, made by `tools/mockdata`) holds references only: placepix
ids, GeoNames ids, exact points, times, evidence ids and the composed insight text, never a
verse or a hadith. Rows are written through the application's own services, so the public
point is the approximate cell of `geo/privacy.py` and the exact point stays in
`map_capture_points`, a post is the copy `publication_service` makes, and a photo key is the
placepix address `photo_service` shows as is. Nothing here ever reaches the photo storage:
the store handed to the services refuses every call.

Before anything is written the file is checked: its version, every text against the
scripture guard (one failure refuses the whole file) and every evidence id against the
store (an insight whose verse or hadith is missing is skipped and reported, never replaced).
A member is recognised by the reserved address `<handle>@mock.tabsira.invalid`, which can
never receive mail: running the import again creates nothing for a member that exists, and
`--clean` deletes every row owned by such accounts and no other.

The whole import is one transaction: it lands complete or not at all.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError, Settings, load_settings
from src.database import dispose_engine, get_sessionmaker
from src.errors import AppError
from src.models.atlas import LocationMeaning, LocationSource, MapCapturePoint, MapEntry
from src.models.consent import Consent, ConsentKind
from src.models.scan import Insight, Scan, ScanOutcome, ScanSource, ScanStatus
from src.models.scripture import Hadith, QuranVerse
from src.models.social import (
    Comment,
    CommentStatus,
    Follow,
    Post,
    PostLike,
    PostStatus,
    PostVisibility,
    Report,
    ReportTarget,
)
from src.models.timeseries import EvidenceExposure
from src.models.user import HANDLE_PATTERN, User
from src.owner import Owner
from src.pipeline.engine import (
    EvidenceRef,
    ExplanationPart,
    HadithRef,
    ProposedInsight,
    QuranRef,
    RelationType,
    SmallStep,
    WhyThis,
)
from src.scans.accept import leaks
from src.scans.workflow import insight_row
from src.schemas.atlas import CapturePointIn
from src.services import (
    atlas_service,
    legal_service,
    photo_service,
    post_service,
    profile_service,
    publication_service,
)
from src.services.insight_table_source import InsightTableSource
from src.storage.base import Storage
from src.storage.photos import PhotoStore

SUPPORTED_VERSION = 1
MOCK_DOMAIN = "mock.tabsira.invalid"
# The size asked of placepix for every photo; the file holds the id alone.
PHOTO_WIDTH = 1200
PHOTO_HEIGHT = 800
# The reaction a member can give today: «أثر» is `post_likes`. `jazak` has no table yet.
LIKE_KIND = "benefited"
CHUNK = 1000
PHOTO_CONSENT_VERSION = "mock"
SCHEME_S3 = "s3"


class MockImportError(Exception):
    """The import or the clean cannot go on; the message says why and is safe to print."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EvidenceIn(_Model):
    surah: int | None = None
    ayah: int | None = None
    collection: str | None = None
    number: str | None = None
    matched_on: str
    relation: RelationType = RelationType.DIRECT


class PartIn(_Model):
    section: Literal["seen", "value", "quran", "sunnah", "life"]
    text: str


class StepIn(_Model):
    text: str
    kind: Literal["text_grounded", "ethical_application", "reflection"] = "reflection"
    grounded_in: list[str] = []


class InsightBodyIn(_Model):
    """What the pipeline made of one photo, by reference: evidence ids and the composed text."""

    title: str
    glimpse: str
    concept: str
    relation: RelationType = RelationType.DIRECT
    clues: list[str] = []
    limits: list[str] = []
    entity_ids: list[str] = []
    quran: EvidenceIn | None = None
    hadith: EvidenceIn | None = None
    explanation: list[PartIn] = []
    small_step: StepIn | None = None


class SceneIn(_Model):
    labels: list[str] = []
    ar: str = ""


class ImageIn(_Model):
    placepix_id: int
    scene: SceneIn = SceneIn()
    insight: InsightBodyIn | None = None


class MemberIn(_Model):
    ref: str
    handle: str
    display_name: str
    joined_at: AwareDatetime


class InsightIn(_Model):
    ref: str
    member: str
    image: int
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    # GeoJSON order: [longitude, latitude].
    point: tuple[float, float]


class PostIn(_Model):
    ref: str
    insight: str
    published_at: AwareDatetime
    reflection: str | None = None


class EntryIn(_Model):
    insight: str
    published_at: AwareDatetime


class FollowIn(_Model):
    # `from` is a Python keyword.
    follower: str = Field(alias="from")
    followee: str = Field(alias="to")
    at: AwareDatetime


class ReactionIn(_Model):
    post: str
    member: str
    kind: str
    at: AwareDatetime


class CommentIn(_Model):
    ref: str
    post: str
    member: str
    parent: str | None = None
    text: str | None = None
    at: AwareDatetime


class MockFile(_Model):
    version: int
    images: list[ImageIn] = []
    members: list[MemberIn] = []
    insights: list[InsightIn] = []
    posts: list[PostIn] = []
    map_entries: list[EntryIn] = []
    follows: list[FollowIn] = []
    reactions: list[ReactionIn] = []
    comments: list[CommentIn] = []


@dataclass
class ImportReport:
    """What one import did, and what it left out and why."""

    members: int = 0
    insights: int = 0
    completions: int = 0
    posts: int = 0
    entries: int = 0
    follows: int = 0
    likes: int = 0
    comments: int = 0
    ignored_reactions: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def lines(self) -> list[str]:
        done = (
            f"members {self.members}, insights {self.insights} ({self.completions} completed), "
            f"posts {self.posts}, atlas entries {self.entries}, follows {self.follows}, "
            f"likes {self.likes}, comments {self.comments}"
        )
        out = [done, f"reactions ignored (no table yet): {self.ignored_reactions}"]
        out += [f"skipped {reason}: {count}" for reason, count in sorted(self.skipped.items())]
        out += [f"evidence missing from the store, insight skipped: {self.missing_evidence}"]
        return out


class _NoStorage:
    """The storage the services get: a placepix key never reaches one, so any call is a bug."""

    def _refuse(self, *_: object, **__: object) -> Any:
        message = "the mock import must never touch the photo storage"
        raise AssertionError(message)

    put = get = exists = delete = copy = signed_url = public_url = _refuse


def _store(settings: Settings) -> PhotoStore:
    storage: Storage = _NoStorage()
    return PhotoStore(storage, settings)


def mock_email(handle: str) -> str:
    return f"{handle.lower()}@{MOCK_DOMAIN}"


def photo_address(placepix_id: int) -> str:
    return f"https://placepix.net/id/{placepix_id}/{PHOTO_WIDTH}/{PHOTO_HEIGHT}"


# ─── What may run, and reading the file ───


def check_allowed(
    settings: Settings,
    *,
    i_understand: bool,
    allow_production: bool = False,
    allow_test_database: bool = False,
) -> None:
    """Refuse unless the person said they understand, and the database is one to write to."""
    if not i_understand:
        message = "this writes or deletes many accounts: pass --i-understand"
        raise MockImportError(message)
    name = make_url(settings.database_url.get_secret_value()).database or ""
    if name.endswith("_test") and not allow_test_database:
        message = f"refusing the test database {name!r}"
        raise MockImportError(message)
    if settings.is_production and not allow_production:
        message = "APP_ENV is production: pass --allow-production to import or clean there"
        raise MockImportError(message)


def read_source(source: str, settings: Settings) -> bytes:
    """Read the file from a path, or from `s3://bucket/key` with the project's own S3 keys."""
    if source.startswith(f"{SCHEME_S3}://"):
        from src.storage.s3 import build_client

        bucket, _, key = source.removeprefix(f"{SCHEME_S3}://").partition("/")
        try:
            body: bytes = build_client(settings).get_object(Bucket=bucket, Key=key)["Body"].read()
        except (ClientError, BotoCoreError) as error:
            message = f"cannot read {source} ({type(error).__name__})"
            raise MockImportError(message) from None
        return body
    try:
        return Path(source).read_bytes()
    except OSError as error:
        message = f"cannot read {source} ({type(error).__name__})"
        raise MockImportError(message) from None


def parse(raw: bytes) -> MockFile:
    """Parse the file; refuse what is not JSON, a version other than 1, or a wrong shape."""
    try:
        document = json.loads(raw)
    except ValueError:
        message = "the file is not JSON"
        raise MockImportError(message) from None
    version = document.get("version") if isinstance(document, dict) else None
    if version != SUPPORTED_VERSION:
        message = f"unsupported file version {version!r}; this importer reads {SUPPORTED_VERSION}"
        raise MockImportError(message)
    try:
        return MockFile.model_validate(document)
    except ValidationError as error:
        message = f"the file has the wrong shape ({error.error_count()} problems)"
        raise MockImportError(message) from None


def texts_of(data: MockFile) -> dict[str, str]:
    """Every free text of the file, keyed by where it is."""
    texts: dict[str, str] = {}
    for image in data.images:
        key = f"image.{image.placepix_id}"
        texts[f"{key}.scene"] = image.scene.ar
        body = image.insight
        if body is None:
            continue
        texts |= {f"{key}.title": body.title, f"{key}.glimpse": body.glimpse}
        texts[f"{key}.concept"] = body.concept
        texts |= {f"{key}.clue.{i}": text for i, text in enumerate(body.clues)}
        texts |= {f"{key}.limit.{i}": text for i, text in enumerate(body.limits)}
        texts |= {f"{key}.part.{i}": part.text for i, part in enumerate(body.explanation)}
        texts |= {f"{key}.{name}": e.matched_on for name, e in _evidence(body)}
        if body.small_step is not None:
            texts[f"{key}.step"] = body.small_step.text
    texts |= {f"post.{p.ref}": p.reflection for p in data.posts if p.reflection}
    texts |= {f"comment.{c.ref}": c.text for c in data.comments if c.text}
    return {key: text for key, text in texts.items() if text.strip()}


def _evidence(body: InsightBodyIn) -> list[tuple[str, EvidenceIn]]:
    return [(n, e) for n, e in (("quran", body.quran), ("hadith", body.hadith)) if e is not None]


async def check_scripture_guard(db: AsyncSession, data: MockFile) -> None:
    """Refuse the whole file when any text looks like scripture or repeats the store."""
    for key, text in texts_of(data).items():
        if await leaks(db, [text], []):
            message = f"the scripture guard refuses the text at {key}; nothing was written"
            raise MockImportError(message)


def _keys(image: ImageIn) -> list[tuple[str, str, str]]:
    """Return the evidence of an image as (kind, first, second) keys."""
    body = image.insight
    if body is None:
        return []
    keys = [("quran", str(e.surah), str(e.ayah)) for _, e in _evidence(body) if _ == "quran"]
    return keys + [
        ("hadith", e.collection or "", e.number or "") for n, e in _evidence(body) if n == "hadith"
    ]


async def _missing_evidence(db: AsyncSession, data: MockFile) -> set[int]:
    """Return the placepix ids of images whose verse or hadith is not in the store."""
    wanted = {key for image in data.images for key in _keys(image)}
    verses = [
        (int(a), int(b)) for kind, a, b in wanted if kind == "quran" and a.isdigit() and b.isdigit()
    ]
    hadiths = [(a, b) for kind, a, b in wanted if kind == "hadith"]
    present: set[tuple[str, str, str]] = set()
    if verses:
        rows = await db.execute(
            select(QuranVerse.surah, QuranVerse.ayah).where(
                tuple_(QuranVerse.surah, QuranVerse.ayah).in_(verses)
            )
        )
        present |= {("quran", str(a), str(b)) for a, b in rows.all()}
    if hadiths:
        found = await db.execute(
            select(Hadith.collection, Hadith.number).where(
                tuple_(Hadith.collection, Hadith.number).in_(hadiths)
            )
        )
        present |= {("hadith", a, b) for a, b in found.all()}
    return {image.placepix_id for image in data.images if not set(_keys(image)) <= present}


# ─── Writing ───


def _proposed(body: InsightBodyIn) -> ProposedInsight:
    def ref(kind: str, evidence: EvidenceIn | None) -> EvidenceRef | None:
        if evidence is None:
            return None
        pointer = (
            QuranRef(surah=evidence.surah or 0, ayah=evidence.ayah or 0)
            if kind == "quran"
            else HadithRef(collection=evidence.collection or "", number=evidence.number or "")
        )
        return EvidenceRef(
            ref=pointer,
            relation=evidence.relation,
            retrieval_score=0.0,
            matched_on=evidence.matched_on,
        )

    step = body.small_step
    return ProposedInsight(
        title=body.title,
        glimpse=body.glimpse,
        entity_ids=body.entity_ids,
        anchor=None,
        relation=body.relation,
        quran=ref("quran", body.quran),
        hadith=ref("hadith", body.hadith),
        explanation=[ExplanationPart(section=p.section, text=p.text) for p in body.explanation],
        why=WhyThis(visible_clues=body.clues, concept=body.concept, limits=body.limits),
        small_step=(
            SmallStep(text=step.text, kind=step.kind, grounded_in=step.grounded_in)
            if step
            else None
        ),
    )


async def _add_member(db: AsyncSession, settings: Settings, member: MemberIn) -> User:
    """Make the account as sign-up does, verified, with the two consent rows and photo consent."""
    user = User(
        email=mock_email(member.handle),
        password_hash=None,
        display_name=member.display_name[:60],
        handle=member.handle,
        public_name=member.display_name[:40],
        email_verified_at=member.joined_at,
        created_at=member.joined_at,
    )
    db.add(user)
    await db.flush()
    profile = await profile_service.ensure_profile(db, user.id)
    legal_service.record_acceptance(db, settings, user.id)
    # Consent rows are append-only (a trigger refuses any update), so their time is set while
    # they are still pending, and the photo consent is written as the service would.
    db.add(
        Consent(
            user_id=user.id,
            kind=ConsentKind.PHOTO_STORAGE,
            version=PHOTO_CONSENT_VERSION,
            granted=True,
        )
    )
    profile.photo_storage_consent = True
    profile.consent_version = PHOTO_CONSENT_VERSION
    # Every pending row is this member's: the earlier ones were flushed.
    for row in [row for row in db.new if isinstance(row, Consent)]:
        row.created_at = member.joined_at
    await db.flush()
    return user


async def _add_insight(
    db: AsyncSession, user: User, item: InsightIn, image: ImageIn, body: InsightBodyIn
) -> Insight:
    scan = Scan(
        user_id=user.id,
        source=ScanSource.UPLOAD,
        status=ScanStatus.DONE,
        outcome=ScanOutcome.INSIGHTS,
        engine="pipeline",
        created_at=item.created_at,
        finished_at=item.created_at,
    )
    db.add(scan)
    await db.flush()
    insight = insight_row(Owner(user_id=user.id), _proposed(body), scan=scan, position=0)
    insight.created_at = item.created_at
    insight.completed_at = item.completed_at
    insight.photo_key = photo_address(image.placepix_id)
    db.add(insight)
    await db.flush()
    return insight


async def _add_post(
    db: AsyncSession,
    settings: Settings,
    store: PhotoStore,
    user: User,
    insight: Insight,
    item: PostIn,
) -> Post | None:
    try:
        publication = await publication_service.create_publication(
            db, InsightTableSource(), user, insight.id, settings, publish_photo=True
        )
    except AppError:
        return None
    post = post_service.create_draft(db, user, publication, item.reflection, PostVisibility.PUBLIC)
    await db.flush()
    # Published as the guard publishes a post without text, but with no moderation-log row:
    # that log is append-only, so a row written here could never be removed by `--clean`.
    post.status = PostStatus.PUBLISHED
    post.reviewed_at = post.submitted_at = post.published_at = item.published_at
    post.created_at = item.published_at
    await db.flush()
    await photo_service.sync_public_copy(db, store, insight.id)
    return post


async def _add_entry(
    db: AsyncSession,
    settings: Settings,
    store: PhotoStore,
    user: User,
    insight: Insight,
    point: tuple[float, float],
    item: EntryIn,
) -> bool:
    body = CapturePointIn(
        longitude=point[0],
        latitude=point[1],
        source=LocationSource.USER_SELECTED,
        meaning=LocationMeaning.CAPTURE_POINT,
        photo=True,
    )
    try:
        await atlas_service.place(db, settings, user, insight.id, body, photos=store)
        await atlas_service.publish(db, user, insight.id, photos=store)
    except AppError:
        return False
    entry = (await db.scalars(select(MapEntry).where(MapEntry.insight_id == insight.id))).one()
    entry.published_at = entry.created_at = item.published_at
    capture = await db.get(MapCapturePoint, entry.id)
    assert capture is not None  # `place` made it
    capture.confirmed_at = item.published_at
    await db.flush()
    return True


async def _bulk(db: AsyncSession, model: type[Follow] | type[PostLike], rows: list[dict]) -> None:  # type: ignore[type-arg]
    for start in range(0, len(rows), CHUNK):
        await db.execute(insert(model).values(rows[start : start + CHUNK]).on_conflict_do_nothing())


@dataclass
class _Run:
    """The state of one import: who exists, what this run created, what it can point at."""

    db: AsyncSession
    settings: Settings
    data: MockFile
    store: PhotoStore
    report: ImportReport = field(default_factory=ImportReport)
    users: dict[str, User] = field(default_factory=dict)
    created: set[str] = field(default_factory=set)
    insights: dict[str, Insight] = field(default_factory=dict)
    posts: dict[str, Post] = field(default_factory=dict)


async def _members(run: _Run) -> None:
    existing = {
        user.email: user
        for user in await run.db.scalars(select(User).where(User.email.endswith(f"@{MOCK_DOMAIN}")))
    }
    taken = {
        handle.lower()
        for handle in await run.db.scalars(select(User.handle).where(User.handle.is_not(None)))
        if handle
    }
    for member in run.data.members:
        email = mock_email(member.handle)
        if email in existing:
            run.users[member.ref] = existing[email]
        elif re.fullmatch(HANDLE_PATTERN, member.handle) is None or member.handle.lower() in taken:
            run.report.skip("member with an unusable or taken handle")
        else:
            run.users[member.ref] = await _add_member(run.db, run.settings, member)
            taken.add(member.handle.lower())
            run.created.add(member.ref)
            run.report.members += 1


async def _insights(run: _Run) -> None:
    images = {image.placepix_id: image for image in run.data.images}
    missing = await _missing_evidence(run.db, run.data)
    for item in run.data.insights:
        image = images.get(item.image)
        if item.member not in run.created:
            run.report.skip("insight of a member already imported or unusable")
        elif image is None or image.insight is None:
            run.report.skip("insight whose image has no pipeline outcome")
        elif item.image in missing:
            run.report.missing_evidence.append(item.ref)
        else:
            run.insights[item.ref] = await _add_insight(
                run.db, run.users[item.member], item, image, image.insight
            )
            run.report.insights += 1
            run.report.completions += item.completed_at is not None


async def _publications(run: _Run) -> None:
    by_ref = {item.ref: item for item in run.data.insights}
    for item in run.data.posts:
        insight = run.insights.get(item.insight)
        post = (
            await _add_post(
                run.db,
                run.settings,
                run.store,
                run.users[by_ref[item.insight].member],
                insight,
                item,
            )
            if insight is not None
            else None
        )
        if post is None:
            run.report.skip("post without a publishable insight")
        else:
            run.posts[item.ref] = post
            run.report.posts += 1
    for entry in run.data.map_entries:
        insight = run.insights.get(entry.insight)
        source = by_ref[entry.insight] if insight is not None else None
        if (
            insight is not None
            and source is not None
            and await _add_entry(
                run.db,
                run.settings,
                run.store,
                run.users[source.member],
                insight,
                source.point,
                entry,
            )
        ):
            run.report.entries += 1
        else:
            run.report.skip("atlas entry without a publishable insight")


async def _graph(run: _Run) -> None:
    follows = [
        {
            "follower_id": run.users[edge.follower].id,
            "followee_id": run.users[edge.followee].id,
            "created_at": edge.at,
        }
        for edge in run.data.follows
        if edge.follower in run.created
        and edge.followee in run.users
        and edge.follower != edge.followee
    ]
    await _bulk(run.db, Follow, follows)
    run.report.follows = len(follows)
    likes = {}
    for reaction in run.data.reactions:
        if reaction.kind != LIKE_KIND:
            run.report.ignored_reactions += 1
        elif reaction.member in run.created and reaction.post in run.posts:
            likes[(reaction.post, reaction.member)] = {
                "post_id": run.posts[reaction.post].id,
                "user_id": run.users[reaction.member].id,
                "created_at": reaction.at,
            }
    await _bulk(run.db, PostLike, list(likes.values()))
    run.report.likes = len(likes)
    await _comments(run)


async def _comments(run: _Run) -> None:
    comments: dict[str, Comment] = {}
    for item in run.data.comments:
        parent = comments.get(item.parent) if item.parent else None
        if not item.text or item.member not in run.created or item.post not in run.posts:
            run.report.skip("comment without a text or a post")
        elif item.parent and parent is None:
            run.report.skip("reply without its comment")
        else:
            comment = Comment(
                post_id=run.posts[item.post].id,
                author_id=run.users[item.member].id,
                parent_id=parent.id if parent else None,
                body=item.text,
            )
            run.db.add(comment)
            await run.db.flush()
            comment.status = CommentStatus.PUBLISHED
            comment.created_at = comment.reviewed_at = item.at
            comments[item.ref] = comment
            run.report.comments += 1
    await run.db.flush()


async def import_file(db: AsyncSession, settings: Settings, data: MockFile) -> ImportReport:
    """
    Write what `data` describes that is not there yet, after the checks; the caller commits.

    Nothing is written for a member whose address already exists: neither the member nor
    anything the file says that member did.
    """
    await check_scripture_guard(db, data)
    run = _Run(db, settings, data, _store(settings))
    await _members(run)
    await _insights(run)
    await _publications(run)
    await _graph(run)
    return run.report


async def clean(db: AsyncSession, settings: Settings) -> int:
    """Delete every row owned by a `@mock.tabsira.invalid` account and no other; return how many accounts."""
    mock = select(User.id).where(User.email.endswith(f"@{MOCK_DOMAIN}"))
    ids = list((await db.scalars(mock)).all())
    if not ids:
        return 0
    store = _store(settings)
    for user_id in ids:
        # Placepix keys are only forgotten: the store above refuses any call.
        await photo_service.remove_all(db, store, user_id)
    posts = select(Post.id).where(Post.author_id.in_(ids))
    comments = select(Comment.id).where(Comment.author_id.in_(ids))
    entries = select(MapEntry.id).where(MapEntry.user_id.in_(ids))
    await db.execute(
        delete(Report).where(
            or_(
                (Report.target_type == ReportTarget.POST) & Report.target_id.in_(posts),
                (Report.target_type == ReportTarget.COMMENT) & Report.target_id.in_(comments),
                (Report.target_type == ReportTarget.MAP_ENTRY) & Report.target_id.in_(entries),
            )
        )
    )
    await db.execute(delete(EvidenceExposure).where(EvidenceExposure.user_id.in_(ids)))
    await db.execute(delete(User).where(User.id.in_(ids)))
    return len(ids)


# ─── The command ───


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def _refuse(line: str) -> int:
    sys.stderr.write(f"{line}\n")
    return 1


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.import_mock",
        description="Import the mock members of a file, or remove every one of them.",
    )
    parser.add_argument("source", nargs="?", help="a path or s3://bucket/key of the v1 file")
    parser.add_argument("--clean", action="store_true", help="delete every mock account and row")
    parser.add_argument("--i-understand", action="store_true", dest="understood")
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args(argv)
    if args.clean == (args.source is not None):
        parser.error("give a file to import, or --clean alone")
    return args


async def execute(
    args: argparse.Namespace,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    *,
    allow_test_database: bool = False,
) -> int:
    """Run what `args` ask; return the exit code. Without a `session_factory` the app's engine is used."""
    try:
        check_allowed(
            settings,
            i_understand=args.understood,
            allow_production=args.allow_production,
            allow_test_database=allow_test_database,
        )
        data = None if args.clean else parse(read_source(args.source, settings))
        factory = session_factory or get_sessionmaker()
        async with factory() as db:
            if data is None:
                removed = await clean(db, settings)
                await db.commit()
                _say(f"removed {removed} mock accounts and everything they own")
                return 0
            report = await import_file(db, settings, data)
            await db.commit()
        for line in report.lines():
            _say(line)
    except MockImportError as error:
        return _refuse(str(error))
    except (SQLAlchemyError, OSError) as error:
        return _refuse(f"Cannot reach the database ({type(error).__name__}). Is it migrated?")
    finally:
        if session_factory is None:
            await dispose_engine()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; return the process exit code."""
    args = _arguments(argv)
    try:
        settings = load_settings()
    except ConfigError as error:
        return _refuse(str(error))
    return asyncio.run(execute(args, settings))


if __name__ == "__main__":
    raise SystemExit(main())
