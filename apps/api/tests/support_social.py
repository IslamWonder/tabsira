"""Fixtures of the social network tests: members with their own browsers, and the scripture they cite."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src import clock
from src.models import (
    Comment,
    CommentStatus,
    HadithClassification,
    InsightPublication,
    Post,
    PostStatus,
    User,
)
from src.scripture.rulings import RulingInput, find_hadith, record_ruling
from src.services.insight_source import HadithRef, InsightSnapshot, QuranRef
from src.services.moderation_guard import GuardVerdict, Outcome
from tests.conftest import PASSPHRASE, browser_for
from tests.helpers import any_id
from tests.scripture.fixtures import store_hadiths, store_quran


@dataclass
class Member:
    """An account and the browser it is signed in with; a guest has a browser and no account."""

    user: User
    http: AsyncClient
    handle: str | None


MakeMember = Callable[..., Awaitable[Member]]


@pytest.fixture
async def make_member(
    make_user: Callable[..., Any], account_app: FastAPI
) -> AsyncIterator[MakeMember]:
    """
    Create accounts with a public identity, each signed in through a browser of its own.

    `identity=False` makes an account with no handle yet, `verified=False` one whose address
    nobody has proven, and `signed_in=False` returns a guest: a browser with no account.
    """
    browsers: list[AsyncClient] = []

    async def create(
        handle: str | None = "reader",
        *,
        verified: bool = True,
        identity: bool = True,
        signed_in: bool = True,
        **columns: Any,
    ) -> Member:
        if not signed_in:
            guest = browser_for(account_app)
            browsers.append(guest)
            return Member(None, guest, None)  # type: ignore[arg-type]
        email = f"{handle or 'member'}@example.com"
        if identity and handle is not None:
            columns = {"handle": handle, "public_name": f"{handle} name", **columns}
        user = await make_user(email, verified=verified, **columns)
        browser = browser_for(account_app)
        browsers.append(browser)
        response = await browser.post("/auth/login", json={"email": email, "password": PASSPHRASE})
        assert response.status_code == 200, response.text
        return Member(user, browser, handle)

    yield create
    for browser in browsers:
        await browser.aclose()


# ─── The insights a post publishes, the scripture it cites, and the guard ───


class FakeInsightSource:
    """The test double of `InsightSource`: insights are added by hand, and owned by one account."""

    def __init__(self) -> None:
        self.snapshots: dict[int, InsightSnapshot] = {}
        self.asked: list[tuple[int, uuid.UUID]] = []

    def add(self, snapshot: InsightSnapshot) -> InsightSnapshot:
        self.snapshots[snapshot.insight_id] = snapshot
        return snapshot

    async def load_for_publishing(
        self, db: AsyncSession, insight_id: int, owner_id: uuid.UUID
    ) -> InsightSnapshot | None:
        self.asked.append((insight_id, owner_id))
        found = self.snapshots.get(insight_id)
        return found if found is not None and found.owner_id == owner_id else None


@dataclass
class FakeGuard:
    """A guard that answers what it is told, and remembers what it was asked."""

    verdict: GuardVerdict = field(default_factory=lambda: GuardVerdict(Outcome.ALLOW, "clear"))
    texts: list[str] = field(default_factory=list)
    during: Callable[[], Awaitable[None]] | None = None

    async def check(self, text: str) -> GuardVerdict:
        self.texts.append(text)
        if self.during is not None:
            await self.during()
        return self.verdict


ALLOW = GuardVerdict(Outcome.ALLOW, "clear")
REVIEW = GuardVerdict(Outcome.REVIEW, "guard_uncertain", {"flagged": ["hate"]})
REJECT = GuardVerdict(Outcome.REJECT, "harassment", {"flagged": ["harassment"]})


@pytest.fixture
def insight_source(account_app: FastAPI) -> FakeInsightSource:
    source = FakeInsightSource()
    account_app.state.insight_source = source
    return source


@pytest.fixture
def guard(account_app: FastAPI) -> FakeGuard:
    fake = FakeGuard()
    account_app.state.text_guard = fake
    return fake


@pytest.fixture
async def scripture(db_session: AsyncSession) -> None:
    """The fixture verses and hadiths, with a صحيح ruling on bukhari 1 and a ضعيف one on bukhari 8."""
    await store_quran(db_session)
    await store_hadiths(db_session)
    for number, classification in (
        ("1", HadithClassification.SAHIH),
        ("8", HadithClassification.DAIF),
    ):
        hadith = await find_hadith(db_session, "bukhari", number)
        assert hadith is not None
        await record_ruling(
            db_session,
            hadith.id,
            RulingInput(
                ruling_text=f"[{classification.value}]",
                scholar="s",
                source_book="b",
                page="1",
                dorar_url="https://dorar.net/h/x",
                classification=classification,
                editor_name="editor",
            ),
        )


def snapshot_for(owner: Member | User, **overrides: Any) -> InsightSnapshot:
    """An insight of `owner` citing 112:1 and bukhari 1, verified, with nothing about a photo."""
    owner_id = owner.user.id if isinstance(owner, Member) else owner.id
    values: dict[str, Any] = {
        "insight_id": any_id(),
        "version": 3,
        "owner_id": owner_id,
        "verified": True,
        "title": "ماء يجري",
        "glimpse": "الماء يعلّمنا الجريان",
        "relation_type": "direct",
        "explanation_excerpt": "شرح موجز من التطبيق",
        "quran_refs": (QuranRef(112, 1),),
        "hadith_refs": (HadithRef("bukhari", "1"),),
        "step_text": "اشرب ماءً بهدوء",
        "concepts": ("water",),
    }
    return InsightSnapshot(**{**values, **overrides})


MakeInsight = Callable[..., InsightSnapshot]


@pytest.fixture
def make_insight(insight_source: FakeInsightSource, scripture: None) -> MakeInsight:
    def make(owner: Member | User, **overrides: Any) -> InsightSnapshot:
        return insight_source.add(snapshot_for(owner, **overrides))

    return make


# ─── Rows made straight in the database, for the tests that do not need the routes ───


async def new_post(db: AsyncSession, author: User, **columns: Any) -> Post:
    """A publication of `author` citing 112:1 and a post on it; `columns` set the post."""
    publication = InsightPublication(
        author_id=author.id,
        insight_id=any_id(),
        insight_version=1,
        title="t",
        glimpse="g",
        relation_type="direct",
        quran_refs=[{"surah": 112, "ayah": 1}],
        hadith_refs=[],
        explanation_excerpt="e",
        concepts=columns.pop("concepts", []),
    )
    db.add(publication)
    await db.flush()
    status = columns.pop("status", PostStatus.DRAFT)
    if status is PostStatus.PUBLISHED:
        columns.setdefault("published_at", clock.utcnow())
    post = Post(author_id=author.id, publication_id=publication.id, status=status, **columns)
    db.add(post)
    await db.flush()
    return post


async def new_comment(db: AsyncSession, post: Post, author: User, **columns: Any) -> Comment:
    """A comment of `author` on `post`, published unless `columns` say otherwise."""
    columns.setdefault("status", CommentStatus.PUBLISHED)
    comment = Comment(
        post_id=post.id, author_id=author.id, body=columns.pop("body", "c"), **columns
    )
    db.add(comment)
    await db.flush()
    return comment
