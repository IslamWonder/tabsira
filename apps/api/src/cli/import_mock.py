"""
Import the mock members that start the platform, or remove them (decision 66, plan 23).

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
A member is recognised by the reserved address `<handle>@mock.tabsira.me`, which can never
receive mail: running the import again creates nothing for a member that exists, and `--clean`
deletes every row owned by such accounts and no other. A real member's rows that depend on
mock ones (a comment under a mock post, a reaction, a follow, a report) are counted first and
only removed with `--also-dependent-rows`.

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
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import and_, delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src import security
from src.config import ConfigError, Settings, load_settings
from src.database import dispose_engine, get_sessionmaker
from src.errors import AppError
from src.mock_accounts import MOCK_DOMAINS, mock_email
from src.models.atlas import (
    SPONSOR_REFLECTION_MAX,
    LocationMeaning,
    LocationSource,
    MapCapturePoint,
    MapEntry,
    MapEntrySponsorship,
)
from src.models.consent import Consent, ConsentKind
from src.models.profile import (
    AgeRange,
    Gender,
    Goal,
    KnowledgeLevel,
    ReducedMotion,
    ReligiousBackground,
    Theme,
)
from src.models.scan import (
    FeedbackReason,
    FeedbackState,
    Insight,
    InsightFeedback,
    Scan,
    ScanOutcome,
    ScanSource,
    ScanStatus,
)
from src.models.scripture import Hadith, QuranVerse
from src.models.social import (
    COMMENT_MAX,
    REFLECTION_MAX,
    Block,
    Bookmark,
    Comment,
    CommentStatus,
    Follow,
    Post,
    PostReaction,
    PostStatus,
    PostVisibility,
    ReactionKind,
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
from src.schemas.social import clean_text
from src.services import (
    atlas_service,
    completion_service,
    legal_service,
    orphan_service,
    photo_service,
    post_service,
    profile_service,
    public_identity,
    publication_service,
    sponsorship_service,
)
from src.services.insight_table_source import InsightTableSource
from src.services.post_service import looks_like_scripture
from src.storage.base import Storage, is_mock_photo_address
from src.storage.photos import PhotoStore

SUPPORTED_VERSION = 1
# The size asked of placepix when the file gives an image's id without its address.
PHOTO_WIDTH = 1080
PHOTO_HEIGHT = 1080
# The most a file may weigh: the real one is about 5 MB.
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PLACEPIX_ID = 10**9
NAME_MAX = 60
# What a member's text may not hold whatever the guards say: an address, a link, a number to call.
_UNSAFE_TEXT = re.compile(
    r"(https?://|www\.|\b[\w-]+\.(?:com|net|org|me|io|info|app|co|tv|ly|xyz|ru|cn)\b|\S@\S|@\w|\+?\d[\d\s().-]{7,}\d)",
    re.IGNORECASE,
)
CHUNK = 1000
# The one password of every mock member, an owners' decision for the contest's judges; hashed
# like any password, with the configured rounds. Production is reset at launch.
MOCK_PASSWORD = "tabsira"  # noqa: S105
# The profile form is filled a few minutes after the account is made.
PROFILE_DELAY = timedelta(minutes=3)
TEMPLATE_DATABASE = "tabsira_template"
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
    placepix_id: int = Field(ge=1, le=MAX_PLACEPIX_ID)
    url: str | None = None
    scene: SceneIn = SceneIn()
    insight: InsightBodyIn | None = None


class MemberIn(_Model):
    ref: str
    handle: str
    display_name: str
    joined_at: AwareDatetime
    # What the person declared at sign-up and in the profile form: private, as for every member.
    gender: Gender = Gender.UNKNOWN
    age_range: AgeRange = AgeRange.UNKNOWN
    goals: list[Goal] = []
    knowledge_level: KnowledgeLevel = KnowledgeLevel.UNKNOWN
    religious_background: ReligiousBackground = ReligiousBackground.UNKNOWN
    theme: Theme = Theme.SYSTEM
    reduced_motion: ReducedMotion = ReducedMotion.SYSTEM
    sound: bool = False
    # Whether the person ticked the box that shows the full name beside the handle (decision 64).
    public_full_name: bool = False

    @field_validator("age_range")
    @classmethod
    def _not_a_child(cls, value: AgeRange) -> AgeRange:
        if value is AgeRange.UNDER_13:
            message = "a mock member is never under 13"
            raise ValueError(message)
        return value


class FeedbackIn(_Model):
    helpful: bool
    reasons: list[FeedbackReason] = []
    at: AwareDatetime


class InsightIn(_Model):
    ref: str
    member: str
    image: int
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    # GeoJSON order: [longitude, latitude].
    point: tuple[float, float]
    feedback: FeedbackIn | None = None


class PostIn(_Model):
    ref: str
    insight: str
    published_at: AwareDatetime
    reflection: str | None = None
    visibility: PostVisibility = PostVisibility.PUBLIC
    # Whether the post shows the insight's photo (the owner's choice, v2 §19).
    photo: bool = True


class SponsorIn(_Model):
    """The member who looks after an orphaned entry, and the words they left under it."""

    member: str
    at: AwareDatetime
    reflection: str | None = None


class EntryIn(_Model):
    insight: str
    published_at: AwareDatetime
    # Quiet for 30 days: widened by the daily job's own function, and maybe looked after since.
    orphaned: bool = False
    sponsor: SponsorIn | None = None


class FollowIn(_Model):
    # `from` is a Python keyword.
    follower: str = Field(alias="from")
    followee: str = Field(alias="to")
    at: AwareDatetime


class BlockIn(FollowIn):
    pass


class ReactionIn(_Model):
    post: str
    member: str
    kind: str
    at: AwareDatetime


class BookmarkIn(_Model):
    post: str
    member: str
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
    blocks: list[BlockIn] = []
    reactions: list[ReactionIn] = []
    bookmarks: list[BookmarkIn] = []
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
    blocks: int = 0
    likes: int = 0
    bookmarks: int = 0
    comments: int = 0
    sponsorships: int = 0
    orphaned: int = 0
    ignored_reactions: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def lines(self) -> list[str]:
        done = (
            f"members {self.members}, insights {self.insights} ({self.completions} completed), "
            f"posts {self.posts}, atlas entries {self.entries} ({self.orphaned} orphaned, "
            f"{self.sponsorships} sponsored), follows {self.follows}, blocks {self.blocks}, "
            f"reactions {self.likes}, bookmarks {self.bookmarks}, comments {self.comments}"
        )
        out = [done, f"reactions of an unknown kind, ignored: {self.ignored_reactions}"]
        out += [f"skipped {reason}: {count}" for reason, count in sorted(self.skipped.items())]
        out += [f"evidence missing from the store, insight skipped: {self.missing_evidence}"]
        return out


class _NoStorage:
    """The storage the services get: a placepix key never reaches one, so any call is a bug."""

    def _refuse(self, *_: object, **__: object) -> Any:
        message = "the mock import must never touch the photo storage"
        raise AssertionError(message)

    put = get = exists = delete = copy = delete_prefix = signed_url = public_url = _refuse


def _store(settings: Settings) -> PhotoStore:
    storage: Storage = _NoStorage()
    return PhotoStore(storage, settings)


def photo_address(image: ImageIn) -> str:
    """Return the file's own placepix address of the image, or the default size of its id."""
    if is_mock_photo_address(image.url):
        return str(image.url)
    return f"https://placepix.net/id/{image.placepix_id}/{PHOTO_WIDTH}/{PHOTO_HEIGHT}"


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
    if (name.endswith("_test") or name == TEMPLATE_DATABASE) and not allow_test_database:
        message = f"refusing the test database {name!r}"
        raise MockImportError(message)
    if settings.is_production and not allow_production:
        message = "APP_ENV is production: pass --allow-production to import or clean there"
        raise MockImportError(message)


def _too_big(source: str) -> MockImportError:
    return MockImportError(f"{source} is larger than {MAX_FILE_BYTES // 2**20} MB: refused")


def read_source(source: str, settings: Settings) -> bytes:
    """Read the file from a path, or from `s3://bucket/key` with the project's own S3 keys."""
    if source.startswith(f"{SCHEME_S3}://"):
        from src.storage.s3 import build_client

        bucket, _, key = source.removeprefix(f"{SCHEME_S3}://").partition("/")
        try:
            answer = build_client(settings).get_object(Bucket=bucket, Key=key)
            # The size is asked first, and the read is capped anyway: the length may be missing.
            if int(answer.get("ContentLength") or 0) > MAX_FILE_BYTES:
                raise _too_big(source)
            body: bytes = answer["Body"].read(MAX_FILE_BYTES + 1)
        except (ClientError, BotoCoreError) as error:
            message = f"cannot read {source} ({type(error).__name__})"
            raise MockImportError(message) from None
        if len(body) > MAX_FILE_BYTES:
            raise _too_big(source)
        return body
    try:
        if Path(source).stat().st_size > MAX_FILE_BYTES:
            raise _too_big(source)
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
    for member in data.members:
        texts[f"member.{member.ref}.handle"] = member.handle
        texts[f"member.{member.ref}.display_name"] = member.display_name
    texts |= {f"post.{p.ref}": p.reflection for p in data.posts if p.reflection}
    texts |= {f"comment.{c.ref}": c.text for c in data.comments if c.text}
    texts |= {
        f"sponsor.{e.insight}": e.sponsor.reflection
        for e in data.map_entries
        if e.sponsor and e.sponsor.reflection
    }
    return {key: text for key, text in texts.items() if text.strip()}


def text_problem(text: str, limit: int) -> str | None:
    """
    Return why a member's text may not be shown, or None.

    What a member's own text goes through before anyone reads it: the schemas' cleaning (control
    characters, bidirectional overrides, length) and the scripture look-alike check of a post,
    then what no text of ours may carry: a link, an address, a number to call.
    """
    try:
        cleaned = clean_text(text, limit)
    except ValueError:
        return "control characters or too long"
    if cleaned is None:
        return "empty"
    if looks_like_scripture(cleaned):
        return "reads like scripture"
    if _UNSAFE_TEXT.search(cleaned):
        return "a link, an address or a number"
    return None


def member_texts_of(data: MockFile) -> dict[str, tuple[str, int]]:
    """Every text a member wrote or is named by, with the longest the app allows for it."""
    found: dict[str, tuple[str, int]] = {}
    for member in data.members:
        found[f"member.{member.ref}.handle"] = (member.handle, NAME_MAX)
        found[f"member.{member.ref}.display_name"] = (member.display_name, NAME_MAX)
    found |= {f"post.{p.ref}": (p.reflection, REFLECTION_MAX) for p in data.posts if p.reflection}
    found |= {f"comment.{c.ref}": (c.text, COMMENT_MAX) for c in data.comments if c.text}
    found |= {
        f"sponsor.{e.insight}": (e.sponsor.reflection, SPONSOR_REFLECTION_MAX)
        for e in data.map_entries
        if e.sponsor and e.sponsor.reflection
    }
    return found


def check_member_texts(data: MockFile) -> None:
    """Refuse the whole file when any member text fails the app's own checks."""
    for key, (text, limit) in member_texts_of(data).items():
        problem = text_problem(text, limit)
        if problem is not None:
            message = f"the text at {key} is refused ({problem}); nothing was written"
            raise MockImportError(message)


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


async def _add_member(
    db: AsyncSession, settings: Settings, member: MemberIn, password_hash: str
) -> User:
    """
    Make the account as sign-up and the profile form leave it.

    Verified, signed in with the shared password, both legal texts accepted at the current
    versions, the profile complete.
    """
    user = User(
        email=mock_email(member.handle),
        password_hash=password_hash,
        display_name=member.display_name[:60],
        handle=member.handle,
        public_name=member.display_name[:40],
        public_full_name=member.public_full_name,
        email_verified_at=member.joined_at,
        created_at=member.joined_at,
    )
    db.add(user)
    await db.flush()
    profile = await profile_service.ensure_profile(db, user.id)
    legal_service.record_acceptance(db, settings, user.id)
    # Consent rows are append-only (a trigger refuses any update), so their time is set while
    # they are still pending. The photo consent and the full-name answer are what the profile
    # form records, at the privacy text's version, the one the person last answered.
    for kind, granted in (
        (ConsentKind.PHOTO_STORAGE, True),
        (ConsentKind.PUBLIC_FULL_NAME, member.public_full_name),
    ):
        db.add(
            Consent(user_id=user.id, kind=kind, version=settings.privacy_version, granted=granted)
        )
    profile.photo_storage_consent = True
    profile.consent_version = settings.privacy_version
    profile.goals = [goal.value for goal in member.goals]
    profile.knowledge_level = member.knowledge_level
    profile.age_range = member.age_range
    profile.religious_background = member.religious_background
    profile.gender = member.gender
    profile.language = "ar"
    profile.theme = member.theme
    profile.reduced_motion = member.reduced_motion
    profile.sound_enabled = member.sound
    profile.questions_asked = True
    profile.profile_completed_at = member.joined_at + PROFILE_DELAY
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
    owner = Owner(user_id=user.id)
    insight = insight_row(owner, _proposed(body), scan=scan, position=0)
    insight.created_at = item.created_at
    insight.completed_at = item.completed_at
    address = photo_address(image)
    # The column only ever holds an address placepix serves: never a key of our storage.
    assert is_mock_photo_address(address)
    insight.photo_key = address
    db.add(insight)
    await db.flush()
    if item.completed_at is not None:
        # What the first «تمّ» writes, by the same functions, at the time the file gives. A mock
        # insight has no learning unit (the pipeline gives scans none), so no unit state is made,
        # exactly as for a member's own scan.
        await completion_service.remember(db, owner, insight)
        await completion_service.place_in_world(db, owner, insight, treasure=True)
    if item.feedback is not None:
        db.add(
            InsightFeedback(
                insight_id=insight.id,
                helpful=item.feedback.helpful,
                reasons=[reason.value for reason in item.feedback.reasons],
                note=None,
                # Nothing waits in the admin queue.
                state=FeedbackState.REVIEWED,
                created_at=item.feedback.at,
                updated_at=item.feedback.at,
            )
        )
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
            db, InsightTableSource(), user, insight.id, settings, publish_photo=item.photo
        )
    except AppError:
        return None
    post = post_service.create_draft(db, user, publication, item.reflection, item.visibility)
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
    run: _Run,
    user: User,
    insight: Insight,
    point: tuple[float, float],
    item: EntryIn,
) -> bool:
    db, store = run.db, run.store
    body = CapturePointIn(
        longitude=point[0],
        latitude=point[1],
        source=LocationSource.USER_SELECTED,
        meaning=LocationMeaning.CAPTURE_POINT,
        photo=True,
    )
    try:
        await atlas_service.place(db, run.settings, user, insight.id, body, photos=store)
        await atlas_service.publish(db, user, insight.id, photos=store)
    except AppError:
        return False
    entry = (await db.scalars(select(MapEntry).where(MapEntry.insight_id == insight.id))).one()
    entry.published_at = entry.created_at = entry.last_active_at = item.published_at
    capture = await db.get(MapCapturePoint, entry.id)
    assert capture is not None  # `place` made it
    capture.confirmed_at = item.published_at
    await db.flush()
    if item.orphaned:
        return await _orphan(run, entry.id, insight.id, item)
    return True


async def _orphan(run: _Run, entry_id: int, insight_id: int, item: EntryIn) -> bool:
    """Orphan the entry as the daily job does, then let its sponsor look after it."""
    db = run.db
    # The job's own function: it widens the place, writes the generalisation row and gives the
    # entry its new public id; the cutoff is the start of today, later than any time of the file.
    marked = await orphan_service.mark_one(db, entry_id, orphan_service.cutoff_for(0), run.store)
    if marked is not orphan_service.Marked.WIDENED:
        message = f"the entry of insight {insight_id} could not be orphaned"
        raise MockImportError(message)
    entry = (await db.scalars(select(MapEntry).where(MapEntry.insight_id == insight_id))).one()
    sponsor = item.sponsor
    if sponsor is None or sponsor.member not in run.users:
        return True
    try:
        sponsorship = await sponsorship_service.start(db, run.users[sponsor.member], entry.id)
    except AppError:
        run.report.skip("sponsorship refused by the app")
        return True
    sponsorship.started_at = entry.last_active_at = sponsor.at
    if sponsor.reflection:
        # Judged beforehand, as the guard would: published, with no moderation-log row.
        sponsorship.reflection = sponsor.reflection
        sponsorship.reflection_status = CommentStatus.PUBLISHED
    await db.flush()
    run.report.sponsorships += 1
    return True


async def _bulk(
    db: AsyncSession,
    model: type[Follow] | type[PostReaction] | type[Bookmark] | type[Block],
    rows: list[dict],  # type: ignore[type-arg]
) -> None:
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


def _on_mock_domain() -> Any:
    return or_(*(User.email.endswith(f"@{domain}") for domain in MOCK_DOMAINS))


async def _mock_users(db: AsyncSession) -> list[User]:
    return list(await db.scalars(select(User).where(_on_mock_domain())))


async def _members(run: _Run) -> None:
    existing = {user.email.split("@")[0]: user for user in await _mock_users(run.db)}
    taken = {
        handle.lower()
        for handle in await run.db.scalars(select(User.handle).where(User.handle.is_not(None)))
        if handle
    }
    # One hash for the run: the same password, hashed by the app's own function in a thread.
    password_hash = await asyncio.to_thread(
        security.hash_password, MOCK_PASSWORD, run.settings.password_bcrypt_rounds
    )
    for member in run.data.members:
        name = member.handle.lower()
        if name in existing:
            run.users[member.ref] = existing[name]
        elif (
            re.fullmatch(HANDLE_PATTERN, member.handle) is None
            or name in taken
            or public_identity.handle_problem(public_identity.clean_handle(member.handle))
        ):
            run.report.skip("member with an unusable or taken handle")
        else:
            run.users[member.ref] = await _add_member(run.db, run.settings, member, password_hash)
            taken.add(name)
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
            and await _add_entry(run, run.users[source.member], insight, source.point, entry)
        ):
            run.report.entries += 1
            run.report.orphaned += entry.orphaned
        else:
            run.report.skip("atlas entry without a publishable insight")


async def _graph(run: _Run) -> None:
    blocked = {frozenset((edge.follower, edge.followee)) for edge in run.data.blocks}
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
        # A block ends the follows between two accounts: none is written across one.
        and frozenset((edge.follower, edge.followee)) not in blocked
    ]
    await _bulk(run.db, Follow, follows)
    run.report.follows = len(follows)
    blocks = [
        {
            "blocker_id": run.users[edge.follower].id,
            "blocked_id": run.users[edge.followee].id,
            "created_at": edge.at,
        }
        for edge in run.data.blocks
        if edge.follower in run.created
        and edge.followee in run.created
        and edge.follower != edge.followee
    ]
    await _bulk(run.db, Block, blocks)
    run.report.blocks = len(blocks)
    likes: dict[tuple[str, str, str], dict[str, Any]] = {}
    kinds = {kind.value: kind for kind in ReactionKind}
    for reaction in run.data.reactions:
        if reaction.kind not in kinds:
            run.report.ignored_reactions += 1
        elif reaction.member in run.created and reaction.post in run.posts:
            likes[(reaction.post, reaction.member, reaction.kind)] = {
                "post_id": run.posts[reaction.post].id,
                "user_id": run.users[reaction.member].id,
                "kind": kinds[reaction.kind],
                "created_at": reaction.at,
            }
    await _bulk(run.db, PostReaction, list(likes.values()))
    run.report.likes = len(likes)
    saved = {
        (mark.post, mark.member): {
            "post_id": run.posts[mark.post].id,
            "user_id": run.users[mark.member].id,
            "created_at": mark.at,
        }
        for mark in run.data.bookmarks
        if mark.member in run.created and mark.post in run.posts
    }
    await _bulk(run.db, Bookmark, list(saved.values()))
    run.report.bookmarks = len(saved)
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
    anything the file says that member did. The services run with every feature on, whatever the
    host's switches say (decision 63): the rows are the same on a host that turns the atlas or
    the network on later, and a photo of a post is not refused by the photo switch.
    """
    await check_scripture_guard(db, data)
    check_member_texts(data)
    settings = settings.model_copy(update={"disabled_features": "", "enabled_features": ""})
    run = _Run(db, settings, data, _store(settings))
    await _members(run)
    await _insights(run)
    await _publications(run)
    await _graph(run)
    return run.report


@dataclass
class CleanReport:
    """What `clean` removed: accounts, and the rows of other members that depended on them."""

    accounts: int = 0
    dependents: dict[str, int] = field(default_factory=dict)


async def _count(db: AsyncSession, model: Any, *conditions: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


async def dependent_rows(db: AsyncSession, ids: list[Any]) -> dict[str, int]:
    """
    Count what other members have written that hangs on the mock accounts, by kind.

    Deleting an account removes by cascade what is attached to its posts, comments and entries,
    whoever wrote it: a real member's comment, reaction, bookmark or sponsorship, a follow or a
    block, and a report that names mock content.
    """
    posts = select(Post.id).where(Post.author_id.in_(ids))
    comments = select(Comment.id).where(Comment.author_id.in_(ids))
    entries = select(MapEntry.id).where(MapEntry.user_id.in_(ids))
    sponsorships = select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id.in_(entries))
    other = Comment.author_id.not_in(ids)
    found = {
        "comments or replies": await _count(
            db, Comment, other, or_(Comment.post_id.in_(posts), Comment.parent_id.in_(comments))
        ),
        "reactions": await _count(
            db, PostReaction, PostReaction.user_id.not_in(ids), PostReaction.post_id.in_(posts)
        ),
        "bookmarks": await _count(
            db, Bookmark, Bookmark.user_id.not_in(ids), Bookmark.post_id.in_(posts)
        ),
        "follows": await _count(
            db,
            Follow,
            or_(
                and_(Follow.followee_id.in_(ids), Follow.follower_id.not_in(ids)),
                and_(Follow.follower_id.in_(ids), Follow.followee_id.not_in(ids)),
            ),
        ),
        "blocks": await _count(
            db,
            Block,
            or_(
                and_(Block.blocked_id.in_(ids), Block.blocker_id.not_in(ids)),
                and_(Block.blocker_id.in_(ids), Block.blocked_id.not_in(ids)),
            ),
        ),
        "sponsorships": await _count(
            db,
            MapEntrySponsorship,
            or_(
                and_(
                    MapEntrySponsorship.entry_id.in_(entries),
                    MapEntrySponsorship.user_id.not_in(ids),
                ),
                and_(
                    MapEntrySponsorship.user_id.in_(ids),
                    MapEntrySponsorship.entry_id.not_in(entries),
                ),
            ),
        ),
        "reports": await _count(
            db,
            Report,
            Report.reporter_id.not_in(ids),
            or_(
                (Report.target_type == ReportTarget.POST) & Report.target_id.in_(posts),
                (Report.target_type == ReportTarget.COMMENT) & Report.target_id.in_(comments),
                (Report.target_type == ReportTarget.MAP_ENTRY) & Report.target_id.in_(entries),
                (Report.target_type == ReportTarget.SPONSORSHIP)
                & Report.target_id.in_(sponsorships),
            ),
        ),
    }
    return {kind: number for kind, number in found.items() if number}


async def clean(
    db: AsyncSession, settings: Settings, *, also_dependent_rows: bool = False
) -> CleanReport:
    """
    Delete every row owned by a mock account and no other.

    Rows of other members that depend on mock accounts are counted first; without
    `also_dependent_rows` the clean refuses and removes nothing. A photo key of a mock insight is
    a placepix address and the rows go by cascade: the photo storage is never called.
    """
    ids = list((await db.scalars(select(User.id).where(_on_mock_domain()))).all())
    if not ids:
        return CleanReport()
    dependents = await dependent_rows(db, ids)
    if dependents and not also_dependent_rows:
        counts = ", ".join(f"{kind} {number}" for kind, number in dependents.items())
        message = (
            f"rows of other members depend on the mock accounts ({counts}): "
            "nothing was removed; pass --also-dependent-rows to remove them too"
        )
        raise MockImportError(message)
    posts = select(Post.id).where(Post.author_id.in_(ids))
    comments = select(Comment.id).where(Comment.author_id.in_(ids))
    entries = select(MapEntry.id).where(MapEntry.user_id.in_(ids))
    sponsorships = select(MapEntrySponsorship.id).where(MapEntrySponsorship.entry_id.in_(entries))
    await db.execute(
        delete(Report).where(
            or_(
                (Report.target_type == ReportTarget.POST) & Report.target_id.in_(posts),
                (Report.target_type == ReportTarget.COMMENT) & Report.target_id.in_(comments),
                (Report.target_type == ReportTarget.MAP_ENTRY) & Report.target_id.in_(entries),
                (Report.target_type == ReportTarget.SPONSORSHIP)
                & Report.target_id.in_(sponsorships),
            )
        )
    )
    await db.execute(delete(EvidenceExposure).where(EvidenceExposure.user_id.in_(ids)))
    await db.execute(delete(User).where(User.id.in_(ids)))
    return CleanReport(len(ids), dependents)


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
    parser.add_argument(
        "--also-dependent-rows",
        action="store_true",
        help="with --clean: also remove other members' comments, reactions, follows and reports "
        "that hang on mock accounts (they are counted and refused otherwise)",
    )
    args = parser.parse_args(argv)
    if args.clean == (args.source is not None):
        parser.error("give a file to import, or --clean alone")
    if args.also_dependent_rows and not args.clean:
        parser.error("--also-dependent-rows goes with --clean")
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
                removed = await clean(db, settings, also_dependent_rows=args.also_dependent_rows)
                await db.commit()
                _say(f"removed {removed.accounts} mock accounts and everything they own")
                for kind, number in removed.dependents.items():
                    _say(f"removed {number} {kind} of other members")
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
