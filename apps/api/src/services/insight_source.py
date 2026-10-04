"""
Where a post's insight comes from: the one seam between the social network and the insights.

Publishing never reads the insights table directly. It asks an `InsightSource` for the
facts about one insight, and builds the publication from them (`publication_service`). The
insights feature implements this protocol over its own table and hands the implementation
to `create_app(insight_source=...)`; tests use a double. A source returns what the
insight is, never what to do with it: whether the photo may be published, whether the
evidence still holds and what is copied are decided here, so no source can widen them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class QuranRef:
    """A verse by its place in the mushaf; never its text."""

    surah: int
    ayah: int


@dataclass(frozen=True)
class HadithRef:
    """A hadith by its book and the dataset's own number; never its text."""

    collection: str
    number: str


@dataclass(frozen=True)
class InsightSnapshot:
    """
    One insight as it is at the moment of publishing, with only what a post copies.

    `insight_id` is the insight's public id (decision 37), `owner_id` its owner's account id.
    `verified` says the insight passed the evidence gate when it was made. The photo
    fields are the owner's facts: `photo_ref` is an opaque reference to the stored
    photo, `photo_consent` says the owner agreed to publish it, `scene_sensitive` says
    the scene was judged sensitive. Text fields are the platform's words, never the
    author's and never scripture.
    """

    insight_id: int
    version: int
    owner_id: uuid.UUID
    verified: bool
    title: str
    glimpse: str
    relation_type: str
    explanation_excerpt: str
    quran_refs: tuple[QuranRef, ...] = ()
    hadith_refs: tuple[HadithRef, ...] = ()
    step_text: str | None = None
    concepts: tuple[str, ...] = field(default_factory=tuple)
    photo_ref: str | None = None
    photo_consent: bool = False
    scene_sensitive: bool = False


class InsightSource(Protocol):
    """What the social network needs from the insights."""

    async def load_for_publishing(
        self, db: AsyncSession, insight_id: int, owner_id: uuid.UUID
    ) -> InsightSnapshot | None:
        """
        Return the insight, or None when there is none with this id owned by `owner_id`.

        Ownership is the source's to check: an id that belongs to someone else answers
        exactly as one that does not exist.
        """
