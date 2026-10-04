"""
What the account export says about the social network: everything the account wrote or did.

The owner gets their own words back (posts, reflections, comments, reports with their details),
what they published of an insight, and the lists of what they did (follows, blocks, likes,
bookmarks). Other people appear only as the handle they chose to be known by.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.models.social import (
    CommentStatus,
    PostStatus,
    PostVisibility,
    RemovalSource,
    ReportReason,
    ReportStatus,
    ReportTarget,
)
from src.schemas.public_id import PublicId


class PublicationExport(BaseModel):
    """The copy of an insight a post published: references to the evidence, never scripture."""

    model_config = ConfigDict(from_attributes=True)

    id: PublicId
    insight_id: PublicId
    insight_version: int
    title: str
    glimpse: str
    relation_type: str
    concepts: list[str]
    quran_refs: list[dict[str, Any]]
    hadith_refs: list[dict[str, Any]]
    explanation_excerpt: str
    step_text: str | None
    photo_ref: str | None
    created_at: datetime


class PostExport(BaseModel):
    id: PublicId
    status: PostStatus
    status_reason: str | None
    visibility: PostVisibility
    reflection: str | None
    created_at: datetime
    submitted_at: datetime | None
    published_at: datetime | None
    removed_at: datetime | None
    removal_source: RemovalSource | None
    publication: PublicationExport | None


class CommentExport(BaseModel):
    id: PublicId
    post_id: PublicId
    parent_id: PublicId | None
    body: str
    status: CommentStatus
    status_reason: str | None
    created_at: datetime


class HandleExport(BaseModel):
    """Someone the account follows or blocked, by the handle they chose, and since when."""

    handle: str
    since: datetime


class PostMarkExport(BaseModel):
    """A post the account liked or saved."""

    post_id: PublicId
    at: datetime


class ReportExport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PublicId
    target_type: ReportTarget
    target_id: PublicId
    reason: ReportReason
    details: str | None
    status: ReportStatus
    created_at: datetime


class SocialExport(BaseModel):
    posts: list[PostExport]
    comments: list[CommentExport]
    following: list[HandleExport]
    blocked: list[HandleExport]
    likes: list[PostMarkExport]
    bookmarks: list[PostMarkExport]
    reports: list[ReportExport]
