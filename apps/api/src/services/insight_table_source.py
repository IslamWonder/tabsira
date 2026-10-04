"""
The `InsightSource` of the social network, read from the insights table.

The scan workflow keeps each insight in `app.insights` (src/models/scan.py). Publishing
asks this source for one of them by id and owner, and gets back the facts a post copies
(`InsightSnapshot`), never a decision: whether the insight may be published is settled by
`publication_service`. An insight of a guest, of another account or that does not exist
answers None alike, so an id reveals nothing.

What `verified` means here: the insight came out of the real pipeline (`engine ==
"pipeline"`) and so passed the evidence gate when it was made. A `demo` insight is a
declared simulation and a `prepared` one is a reviewed tutorial copy shared by everyone;
neither is a person's own verified insight, so neither is publishable.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scan import Insight, Scan
from src.models.social import EXPLANATION_MAX
from src.services.insight_source import HadithRef, InsightSnapshot, QuranRef

PUBLISHABLE_ENGINE = "pipeline"
# Where a shortened excerpt may end: the end of an Arabic or Latin sentence.
_SENTENCE_ENDS = ".؟!…"
_ELLIPSIS = "…"


def explanation_excerpt(parts: list[dict[str, Any]], limit: int = EXPLANATION_MAX) -> str:
    """
    Return the platform's explanation as one text that fits `limit` characters.

    The parts are joined in their order, each a sentence or more written by the app. When
    the whole does not fit, it is cut at the last sentence end before the limit, else at the
    last space, and an ellipsis says so. Nothing is added or reworded.
    """
    text = " ".join(str(part.get("text", "")).strip() for part in parts).strip()
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[: limit - len(_ELLIPSIS)]
    cut = max(head.rfind(end) for end in _SENTENCE_ENDS)
    if cut < limit // 2:
        cut = head.rfind(" ")
    if cut <= 0:
        cut = len(head)
    return head[: cut + 1].rstrip() + _ELLIPSIS


def snapshot_of(insight: Insight, scan: Scan | None) -> InsightSnapshot:
    """Return the facts of `insight` a post copies; `scan` is the scan it came from, if any."""
    if insight.user_id is None:
        message = "only an account's insight has a snapshot"
        raise ValueError(message)
    step = insight.small_step or {}
    return InsightSnapshot(
        insight_id=insight.id,
        version=insight.run,
        owner_id=insight.user_id,
        verified=insight.engine == PUBLISHABLE_ENGINE,
        title=insight.title,
        glimpse=insight.glimpse,
        relation_type=insight.relation,
        explanation_excerpt=explanation_excerpt(insight.explanation),
        quran_refs=(
            (QuranRef(insight.quran_surah, insight.quran_ayah),)
            if insight.quran_surah is not None and insight.quran_ayah is not None
            else ()
        ),
        hadith_refs=(
            (HadithRef(insight.hadith_collection, insight.hadith_number),)
            if insight.hadith_collection is not None and insight.hadith_number is not None
            else ()
        ),
        step_text=str(step["text"]) if step.get("text") else None,
        concepts=tuple(insight.entity_ids or ()),
        # No photo is kept with an insight today (src/models/scan.py): nothing to publish.
        photo_ref=None,
        photo_consent=False,
        scene_sensitive=scan is not None and scan.sensitive,
    )


class InsightTableSource:
    """`InsightSource` over `app.insights`: the owner's own insight, or None."""

    async def load_for_publishing(
        self, db: AsyncSession, insight_id: int, owner_id: uuid.UUID
    ) -> InsightSnapshot | None:
        row = (
            await db.execute(
                select(Insight, Scan)
                .outerjoin(Scan, Scan.id == Insight.scan_id)
                .where(Insight.id == insight_id, Insight.user_id == owner_id)
            )
        ).first()
        if row is None:
            return None
        insight, scan = row
        return snapshot_of(insight, scan)
