"""
Request and response bodies of the social network.

What a public response may say about a person is exactly a handle and a public name, and
for a profile the month they joined and three counts. No schema here has a field for an
e-mail address, the account's own name, a private profile answer or a place; a test lists
every field of every schema, so adding one fails the build until it is justified.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.models.scripture import HadithClassification
from src.models.social import (
    COMMENT_MAX,
    REFLECTION_MAX,
    REPORT_DETAILS_MAX,
    CommentStatus,
    PostStatus,
    PostVisibility,
    ReportReason,
    ReportTarget,
)
from src.schemas.public_id import PublicId
from src.services import public_identity

# The id of a post in a path: a positive 64-bit number, so a larger one is a 422, not a database
# error. Documented as the decimal string responses send (decision 37), since it may exceed the
# 2^53 a JavaScript number holds; parsed to an int here.
PostIdPath = Annotated[PublicId, Path(description="The post's public id")]
CommentIdPath = Annotated[PublicId, Path(description="The comment's public id")]


class PublicIdentityIn(BaseModel):
    """The handle and public name an account chooses to appear under."""

    model_config = ConfigDict(extra="forbid")

    handle: Annotated[str, Field(min_length=1, max_length=64)]
    public_name: Annotated[str, Field(min_length=1, max_length=160)]

    @field_validator("handle")
    @classmethod
    def _handle(cls, value: str) -> str:
        handle = public_identity.clean_handle(value)
        problem = public_identity.handle_problem(handle)
        if problem is not None:
            raise ValueError(problem)
        return handle

    @field_validator("public_name")
    @classmethod
    def _public_name(cls, value: str) -> str:
        name = public_identity.clean_public_name(value)
        problem = public_identity.public_name_problem(name)
        if problem is not None:
            raise ValueError(problem)
        return name


class PublicIdentityOut(BaseModel):
    """The caller's own handle and public name; both null until they have chosen."""

    handle: str | None
    public_name: str | None


class MemberOut(BaseModel):
    """A person as the network shows them: the two things they chose, and nothing else."""

    model_config = ConfigDict(from_attributes=True)

    handle: str
    public_name: str


class ViewerRelationOut(BaseModel):
    """How the signed-in viewer stands to a profile."""

    follows: bool
    is_self: bool


class MemberProfileOut(MemberOut):
    """A public profile: who, since when, and three counts read from the rows they count."""

    joined_month: str = Field(description="`YYYY-MM`, in UTC")
    posts_count: int = Field(description="Published public posts")
    followers_count: int
    following_count: int
    viewer: ViewerRelationOut | None = Field(description="Null for a guest")


# ─── Evidence: references in the publication, the stored text in the response ───


class QuranEvidenceOut(BaseModel):
    """A verse read from the scripture store by its reference, exactly as stored."""

    surah: int
    ayah: int
    surah_name: str
    text: str = Field(description="Exactly as stored; never normalised")
    sha256: str = Field(description="SHA-256 of the UTF-8 bytes of `text`")
    source_url: str = Field(description="The quranpedia page of the verse")
    verified: Literal[True] = True


class HadithEvidenceOut(BaseModel):
    """
    A hadith read from the scripture store, shown only while it is eligible.

    Its ruling is صحيح or حسن, or it has no ruling and belongs to the enriched Sunnah file
    (decision 58).
    """

    collection: str
    collection_name: str
    number: str
    text: str = Field(description="Exactly as stored; never normalised")
    sha256: str = Field(description="SHA-256 of the UTF-8 bytes of `text`")
    classification: HadithClassification | None = Field(
        description="The editor's reading of the ruling in force; null when none is recorded yet"
    )
    verification_url: str = Field(
        description="A dorar.net search the reader opens («تحقق في الدرر»)"
    )
    verified: Literal[True] = True


class InsightOut(BaseModel):
    """What a post publishes: the platform's insight, never the author's words."""

    title: str
    glimpse: str
    relation_type: str
    concepts: list[str]
    explanation: str = Field(description="The app's explanation, shortened; written by the app")
    step: str | None = Field(description="The small step the insight suggests")
    has_photo: bool = Field(description="The owner chose to show a photo with it")
    photo_url: str | None = Field(
        description="The address of the photo's public copy, only on a published public post "
        "while the copy exists; null otherwise. Never a storage key."
    )
    insight_version: int
    quran: list[QuranEvidenceOut]
    hadith: list[HadithEvidenceOut]


class ReflectionOut(BaseModel):
    """
    The author's own words.

    They are labelled as the user's text and never carry the verified badge, whatever they say.
    """

    text: str
    source: Literal["user"] = "user"
    verified: Literal[False] = False
    looks_like_scripture: bool = Field(
        description="The text reads like Quran or hadith; it is still only the author's own"
    )


class ViewerPostOut(BaseModel):
    liked: bool
    bookmarked: bool
    is_author: bool


class WhyOut(BaseModel):
    """«لماذا أرى هذا؟»: the one reason a feed item is where it is."""

    code: Literal["followed_author", "fresh", "new_topic", "community"]
    text: str


class PostOut(BaseModel):
    id: PublicId
    author: MemberOut
    insight: InsightOut
    reflection: ReflectionOut | None
    visibility: PostVisibility
    # Only the author sees a state other than published, and why.
    status: PostStatus
    status_reason: str | None
    status_message: str | None = Field(description="What happened to it, in Arabic, for its author")
    published_at: datetime | None
    created_at: datetime
    like_count: int
    comment_count: int
    viewer: ViewerPostOut | None = Field(description="Null for a guest")
    why: WhyOut | None = Field(description="Only in the «لك» feed")


class PostCreateIn(BaseModel):
    """Start a draft from a verified insight."""

    model_config = ConfigDict(extra="forbid")

    insight_id: PublicId
    reflection: Annotated[str, Field(max_length=REFLECTION_MAX * 2)] | None = None
    visibility: PostVisibility = PostVisibility.PUBLIC
    photo: bool = Field(
        default=False,
        description="Show the insight's kept photo with the post; nothing without a kept photo "
        "and the owner's photo consent (v2 §19)",
    )

    @field_validator("reflection")
    @classmethod
    def _reflection(cls, value: str | None) -> str | None:
        return clean_text(value, REFLECTION_MAX)


class PostPatch(BaseModel):
    """Change a draft, or a rejected post, which becomes a draft again."""

    model_config = ConfigDict(extra="forbid")

    reflection: Annotated[str, Field(max_length=REFLECTION_MAX * 2)] | None = None
    visibility: PostVisibility | None = None

    @field_validator("reflection")
    @classmethod
    def _reflection(cls, value: str | None) -> str | None:
        return clean_text(value, REFLECTION_MAX)


class FeedPage(BaseModel):
    """A page of a feed, and how to ask for the next one."""

    items: list[PostOut]
    next_cursor: str | None = Field(description="Pass as `cursor`; null on the last page")
    empty_reason: Literal["follows_nobody", "no_posts"] | None = Field(
        description="Why the first page has nothing, so the client can say so; never invented posts"
    )


class MyPostsPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None


# ─── Comments ───


class CommentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(max_length=COMMENT_MAX * 2)]
    parent_id: PublicId | None = None

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = clean_text(value, COMMENT_MAX)
        if cleaned is None:
            message = "must not be empty"
            raise ValueError(message)
        return cleaned


class CommentOut(BaseModel):
    id: PublicId
    author: MemberOut
    body: str
    created_at: datetime
    # Only its author sees a comment that is not published yet, and why.
    status: CommentStatus
    status_message: str | None
    is_mine: bool
    replies: list[CommentOut]


class CommentPage(BaseModel):
    items: list[CommentOut]
    next_cursor: str | None


# ─── Reactions, reports ───


class ReactionOut(BaseModel):
    liked: bool
    like_count: int


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: ReportTarget
    target_id: PublicId
    reason: ReportReason
    details: Annotated[str, Field(max_length=REPORT_DETAILS_MAX * 2)] | None = None

    @field_validator("details")
    @classmethod
    def _details(cls, value: str | None) -> str | None:
        return clean_text(value, REPORT_DETAILS_MAX)


class ReportOut(BaseModel):
    id: PublicId


# U+202A to U+202E (embeddings and overrides), U+2066 to U+2069 (isolates), and the invisible
# characters that make two different texts look the same or hide words from a reader.
BIDI_OVERRIDES = frozenset(
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
    "\u00ad\u180e\u200b\u2060\u2061\u2062\u2063\u2064\ufeff\u2028\u2029"
)


def clean_text(value: str | None, limit: int) -> str | None:
    """
    Return `value` trimmed, or None when nothing is left.

    Control characters, the bidirectional overrides and isolates (which can make a line of text
    read as something other than what it says), the invisible characters and anything longer than `limit` characters are
    refused. Line breaks and tabs are kept (a reflection has paragraphs), and so are the plain
    right-to-left and left-to-right marks that Arabic text uses.
    """
    if value is None:
        return None
    text = value.strip()
    if any(
        (unicodedata.category(char) == "Cc" and char not in "\n\t") or char in BIDI_OVERRIDES
        for char in text
    ):
        message = "must not contain control characters"
        raise ValueError(message)
    if len(text) > limit:
        message = f"must be at most {limit} characters"
        raise ValueError(message)
    return text or None
