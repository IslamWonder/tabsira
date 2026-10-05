"""
The social network («تبصرة تواصل»): publications, posts, and what people do with them.

A post is made from a verified insight, never from free text. The insight is copied once,
at publish time, into an immutable `InsightPublication` that holds references to the
evidence and never the scripture itself; readers' responses put the stored text in by
reference. The author's own words live apart, in `Post.reflection`, and are labelled as
theirs wherever they are shown.

Nothing here is a counter: reactions, comments and followers are counted from their own
rows, so a count cannot drift from what it counts. Every foreign key to `users` cascades,
so deleting an account removes its posts, comments, follows, reactions, bookmarks, blocks and
reports with it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DDL,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, created_at_column, string_enum
from src.models.public_id import public_id_pk

TITLE_MAX = 200
GLIMPSE_MAX = 600
EXPLANATION_MAX = 1200
STEP_MAX = 400
REFLECTION_MAX = 800
COMMENT_MAX = 500
REPORT_DETAILS_MAX = 500


class PostVisibility(StrEnum):
    PUBLIC = "public"
    FOLLOWERS = "followers"


class PostStatus(StrEnum):
    """Where a post is in its life; the five states of decision 2."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    REMOVED = "removed"


class CommentStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    REMOVED = "removed"


class RemovalSource(StrEnum):
    """Who took a post down: its author (the content is erased) or a moderator (it is kept)."""

    OWNER = "owner"
    MODERATOR = "moderator"


class ReactionKind(StrEnum):
    """What a reader says to a post: it benefited them, or thanks to its author."""

    BENEFITED = "benefited"
    JAZAK = "jazak"


class ReportTarget(StrEnum):
    POST = "post"
    COMMENT = "comment"
    # An entry of the atlas (a place that is wrong, or that gives away private information).
    MAP_ENTRY = "map_entry"


class ReportReason(StrEnum):
    """Why something was reported. The two place reasons are for the atlas, and kept here ready."""

    ABUSE = "abuse"  # إساءة أو مضايقة
    SPAM = "spam"  # محتوى مزعج أو إعلاني
    FALSE_RELIGIOUS_CLAIM = "false_religious_claim"  # نسبة قول ديني إلى غير قائله
    UNAUTHORISED_PHOTO = "unauthorised_photo"  # صورة منشورة دون إذن
    WRONG_PLACE = "wrong_place"  # المكان غير صحيح
    PRIVATE_INFORMATION = "private_information"  # الموقع أو الصورة يكشفان معلومات خاصة
    OTHER = "other"


class ReportStatus(StrEnum):
    OPEN = "open"
    ACTIONED = "actioned"
    DISMISSED = "dismissed"


class Follow(Base):
    """One account follows another. The pair is the key: a second follow changes nothing."""

    __tablename__ = "follows"
    __table_args__ = (
        PrimaryKeyConstraint("follower_id", "followee_id", name="pk_follows"),
        CheckConstraint("follower_id <> followee_id", name="no_self_follow"),
        # Counting an account's followers.
        Index("ix_follows_followee_id", "followee_id"),
    )

    follower_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    followee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = created_at_column()


class Block(Base):
    """One account blocks another. It hides each from the other everywhere and ends their follows."""

    __tablename__ = "blocks"
    __table_args__ = (
        PrimaryKeyConstraint("blocker_id", "blocked_id", name="pk_blocks"),
        CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),
        Index("ix_blocks_blocked_id", "blocked_id"),
    )

    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = created_at_column()


class InsightPublication(Base):
    """
    The immutable copy of a verified insight that a post publishes.

    Made once, from the insight as it was at that moment (its id and version are kept), and
    never edited: the database refuses every UPDATE. It holds references to the evidence
    (surah and ayah, collection and hadith number) and never the scripture itself; a reader's
    response reads the text from the scripture store, exactly as stored. The photo is a
    reference, kept only when its owner consented and the scene is not sensitive.
    """

    __tablename__ = "insight_publications"
    __table_args__ = (
        # Both lists are JSON arrays and together hold at least one reference. CASE keeps the
        # length call from running on a value that is not an array.
        CheckConstraint(
            "CASE WHEN jsonb_typeof(quran_refs) = 'array' AND jsonb_typeof(hadith_refs) = 'array' "
            "THEN jsonb_array_length(quran_refs) + jsonb_array_length(hadith_refs) >= 1 "
            "ELSE false END",
            name="has_evidence",
        ),
        Index("ix_insight_publications_author_id_created_at", "author_id", "created_at"),
        Index("ix_insight_publications_insight_id", "insight_id"),
    )

    id: Mapped[int] = public_id_pk("insight_publications")
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # The insight this was copied from. No foreign key: the insight may be deleted, and the
    # publication, being a copy, does not depend on it.
    insight_id: Mapped[int] = mapped_column(BigInteger)
    insight_version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(TITLE_MAX))
    glimpse: Mapped[str] = mapped_column(String(GLIMPSE_MAX))
    relation_type: Mapped[str] = mapped_column(String(32))
    # Concept labels of the ontology, for the feed's variety; never shown as a claim.
    concepts: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]")
    )
    # Lists of objects with `surah` and `ayah`, and with `collection` and `number`.
    quran_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    hadith_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # The platform's explanation, shortened; written by the app, never by the author.
    explanation_excerpt: Mapped[str] = mapped_column(String(EXPLANATION_MAX))
    step_text: Mapped[str | None] = mapped_column(String(STEP_MAX))
    # An opaque reference to a photo the owner agreed to publish.
    photo_ref: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = created_at_column()


# The same statements are written out in the migration that creates the table; this copy
# builds the trigger when a test schema is created from the models.
PUBLICATION_IMMUTABLE_STATEMENTS = (
    """
    CREATE OR REPLACE FUNCTION app.insight_publications_forbid_update() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'insight publications are immutable'
            USING ERRCODE = 'integrity_constraint_violation';
    END
    $$
    """,
    """
    CREATE TRIGGER insight_publications_forbid_update BEFORE UPDATE ON app.insight_publications
    FOR EACH ROW EXECUTE FUNCTION app.insight_publications_forbid_update()
    """,
)

for _statement in PUBLICATION_IMMUTABLE_STATEMENTS:
    # SQLAlchemy ships DDL without type hints.
    _ddl = DDL(_statement)  # type: ignore[no-untyped-call]
    event.listen(
        InsightPublication.__table__, "after_create", _ddl.execute_if(dialect="postgresql")
    )


class Post(Base):
    """
    A publication shared with an audience, with the author's own reflection beside it.

    A post an owner withdraws stays as a tombstone (so its address answers 410 Gone): its
    reflection and its publication are erased, its reactions, bookmarks and comments go with it.
    One a moderator removes keeps its content, which an appeal or an audit may need, and is
    hidden from everyone.
    """

    # Read the database-set `updated_at` back with the UPDATE: no lazy load in async code.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="published_has_time"
        ),
        CheckConstraint(
            "status <> 'removed' OR removal_source IS NOT NULL", name="removed_has_source"
        ),
        # The public feed: newest first among what anyone may read.
        Index(
            "ix_posts_public_feed",
            text("published_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'published' AND visibility = 'public'"),
        ),
        # An author's profile and the following feed.
        Index(
            "ix_posts_author_feed",
            "author_id",
            text("published_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'published'"),
        ),
        Index("ix_posts_author_id_created_at", "author_id", text("created_at DESC")),
        # The moderation queue.
        Index(
            "ix_posts_pending_review",
            "created_at",
            postgresql_where=text("status = 'pending_review'"),
        ),
    )

    id: Mapped[int] = public_id_pk("posts")
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    publication_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("insight_publications.id", ondelete="SET NULL"), unique=True
    )
    # The author's own words. Shown as theirs, never with the verified badge.
    reflection: Mapped[str | None] = mapped_column(String(REFLECTION_MAX))
    # Whether the reflection reads like Quran or hadith: it stays the author's text, and the
    # reader is told so.
    reflection_looks_like_scripture: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    visibility: Mapped[PostVisibility] = mapped_column(
        string_enum(PostVisibility, "visibility"),
        default=PostVisibility.PUBLIC,
        server_default=PostVisibility.PUBLIC.value,
    )
    status: Mapped[PostStatus] = mapped_column(
        string_enum(PostStatus, "status"),
        default=PostStatus.DRAFT,
        server_default=PostStatus.DRAFT.value,
    )
    # A code the author is shown with the outcome (see src/messages.py), never a model's words.
    status_reason: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The moderator's account. No foreign key: the decision outlives their account.
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removal_source: Mapped[RemovalSource | None] = mapped_column(
        string_enum(RemovalSource, "removal_source")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PostReaction(Base):
    """A reaction with a meaning (decision 61): one of each kind per account and post."""

    __tablename__ = "post_reactions"
    __table_args__ = (
        PrimaryKeyConstraint("post_id", "user_id", "kind", name="pk_post_reactions"),
        Index("ix_post_reactions_user_id", "user_id"),
    )

    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[ReactionKind] = mapped_column(string_enum(ReactionKind, "kind"))
    created_at: Mapped[datetime] = created_at_column()


class Bookmark(Base):
    """A post a reader saved. Private: nobody sees whose bookmark it is, and nobody counts them."""

    __tablename__ = "bookmarks"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "post_id", name="pk_bookmarks"),
        Index("ix_bookmarks_post_id", "post_id"),
        Index("ix_bookmarks_user_id_created_at", "user_id", text("created_at DESC")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = created_at_column()


class Comment(Base):
    """A comment on a post, or a reply to one: the thread is one level deep."""

    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_post_id_created_at", "post_id", "created_at", "id"),
        Index("ix_comments_parent_id", "parent_id"),
        Index("ix_comments_author_id", "author_id"),
        Index(
            "ix_comments_pending_review",
            "created_at",
            postgresql_where=text("status = 'pending_review'"),
        ),
    )

    id: Mapped[int] = public_id_pk("comments")
    post_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("posts.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Set on a reply, to a comment that has none itself.
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(String(COMMENT_MAX))
    status: Mapped[CommentStatus] = mapped_column(
        string_enum(CommentStatus, "status"),
        default=CommentStatus.PENDING_REVIEW,
        server_default=CommentStatus.PENDING_REVIEW.value,
    )
    status_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class Report(Base):
    """
    A reader's report of a post or a comment, with a reason.

    One per reporter and target. `target_id` names a post or a comment by its id with no
    foreign key (the target type says which), so a report outlives a deleted target, and
    the atlas can report its own entries here later.
    """

    __tablename__ = "reports"
    __table_args__ = (
        Index("uq_reports_reporter_target", "reporter_id", "target_type", "target_id", unique=True),
        Index("ix_reports_target", "target_type", "target_id"),
        Index("ix_reports_open", "created_at", postgresql_where=text("status = 'open'")),
    )

    id: Mapped[int] = public_id_pk("reports")
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[ReportTarget] = mapped_column(string_enum(ReportTarget, "target_type"))
    target_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[ReportReason] = mapped_column(string_enum(ReportReason, "reason"))
    details: Mapped[str | None] = mapped_column(String(REPORT_DETAILS_MAX))
    status: Mapped[ReportStatus] = mapped_column(
        string_enum(ReportStatus, "status"),
        default=ReportStatus.OPEN,
        server_default=ReportStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
