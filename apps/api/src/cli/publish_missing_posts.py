"""
Give every basira published before decision 68 the post it now gets by default.

    uv run python -m src.cli.publish_missing_posts --i-understand [--dry-run] [--allow-production]

Before decision 68 an insight could be public (its page) or placed on the atlas without a post,
so it showed in nobody's publications. This makes the missing post, once, through the same step
the app now takes (`insight_post_service.ensure_post`): public, with no reflection, showing the
photo only where the owner already chose to show it (a published atlas entry with its photo). Safe to run again: an insight that has a post is left alone.

Left out, and counted: an account with no public handle yet, or not verified, or closed; an
insight whose owner withdrew a post since the insight was made (a withdrawn post keeps no link to
its insight, so it may have been this one, and a withdrawal is never undone); an insight with an atlas
entry orphaned once, sponsored or not (it is shown without its author's name on purpose); and an insight the publishing
rules now refuse (its reason is counted).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import ConfigError, Settings, load_settings
from src.database import dispose_engine, get_sessionmaker
from src.errors import AppError
from src.mock_accounts import MOCK_DOMAINS
from src.models.atlas import MapEntry, MapEntryStatus
from src.models.scan import Insight
from src.models.social import Post, RemovalSource
from src.models.user import User
from src.services import insight_post_service
from src.services.insight_table_source import InsightTableSource
from src.services.moderation_guard import GuardVerdict
from src.storage.photos import PhotoStore, build_photo_store

TEMPLATE_DATABASE = "tabsira_template"


class NoTextGuard:
    """A post made here has no words of its author, so the guard is never asked."""

    async def check(self, text: str) -> GuardVerdict:
        message = "a post with no reflection never reaches the guard"
        raise AssertionError(message)


@dataclass
class Report:
    published: int = 0
    skipped: Counter[str] = field(default_factory=Counter)

    def lines(self) -> list[str]:
        out = [f"posts published: {self.published}"]
        out += [f"skipped, {reason}: {count}" for reason, count in sorted(self.skipped.items())]
        return out


def _shown_on_atlas() -> Any:
    return exists().where(
        MapEntry.insight_id == Insight.id,
        MapEntry.user_id == Insight.user_id,
        MapEntry.status == MapEntryStatus.PUBLISHED,
        MapEntry.widened_level.is_(None),
    )


def _anonymised_on_atlas() -> Any:
    # An entry orphaned once stays shown without its author's name, sponsored or not: a post
    # under the author's handle would put the name back on it.
    return exists().where(
        MapEntry.insight_id == Insight.id,
        or_(MapEntry.status == MapEntryStatus.ORPHANED, MapEntry.widened_level.is_not(None)),
    )


async def candidates(db: AsyncSession, *, only_mock: bool = False) -> list[tuple[Insight, User]]:
    """Every insight that is public or shown on the atlas, with its owner, oldest first."""
    query = (
        select(Insight, User)
        .join(User, User.id == Insight.user_id)
        .where(or_(Insight.published_at.is_not(None), _shown_on_atlas()))
        .where(~_anonymised_on_atlas())
        .order_by(Insight.completed_at, Insight.id)
    )
    if only_mock:
        query = query.where(or_(*(User.email.endswith(f"@{domain}") for domain in MOCK_DOMAINS)))
    return [(insight, user) for insight, user in (await db.execute(query)).all()]


async def _withdrew_since(db: AsyncSession, owner_id: uuid.UUID, insight: Insight) -> bool:
    since = insight.completed_at or insight.created_at
    found = await db.scalar(
        select(Post.id)
        .where(
            Post.author_id == owner_id,
            Post.removal_source == RemovalSource.OWNER,
            Post.created_at >= since,
        )
        .limit(1)
    )
    return found is not None


async def _wants_photo(db: AsyncSession, insight: Insight) -> bool:
    """Whether the owner already chose to show the photo with a published atlas entry."""
    shown = await db.scalar(
        select(
            exists().where(
                MapEntry.insight_id == insight.id,
                MapEntry.status == MapEntryStatus.PUBLISHED,
                MapEntry.with_photo.is_(True),
                MapEntry.widened_level.is_(None),
            )
        )
    )
    return bool(shown)


async def _reason_to_skip(db: AsyncSession, insight: Insight, owner: User) -> str | None:
    if not owner.is_active or owner.deleted_at is not None:
        return "account closed"
    if owner.email_verified_at is None:
        return "address not verified"
    if owner.handle is None:
        return "no public handle"
    if await insight_post_service.live_post(db, owner, insight.id) is not None:
        return "already posted"
    if await _withdrew_since(db, owner.id, insight):
        return "owner withdrew a post since"
    return None


async def _fresh(db: AsyncSession, insight_id: int, owner_id: uuid.UUID) -> tuple[Insight, User]:
    fresh = {"populate_existing": True}
    insight = (
        await db.execute(select(Insight).where(Insight.id == insight_id).execution_options(**fresh))
    ).scalar_one()
    owner = (
        await db.execute(select(User).where(User.id == owner_id).execution_options(**fresh))
    ).scalar_one()
    return insight, owner


async def publish_missing(
    db: AsyncSession,
    settings: Settings,
    photos: PhotoStore,
    *,
    dry_run: bool = False,
    only_mock: bool = False,
) -> Report:
    """Publish the missing posts (or, with `dry_run`, only count them); return what happened."""
    report = Report()
    source = InsightTableSource()
    # Ids first: a refusal rolls the session back, which expires every row it had loaded.
    ids = [(insight.id, owner.id) for insight, owner in await candidates(db, only_mock=only_mock)]
    for insight_id, owner_id in ids:
        insight, owner = await _fresh(db, insight_id, owner_id)
        reason = await _reason_to_skip(db, insight, owner)
        if reason is not None:
            report.skipped[reason] += 1
            continue
        if dry_run:
            report.published += 1
            continue
        try:
            await insight_post_service.ensure_post(
                db,
                source,
                owner,
                insight.id,
                settings,
                NoTextGuard(),
                photos,
                publish_photo=await _wants_photo(db, insight),
            )
            await db.commit()
        except AppError as refused:
            # Refused by the publishing rules before anything was added: nothing to undo.
            report.skipped[f"refused ({refused.code})"] += 1
            continue
        report.published += 1
    return report


def check_allowed(
    settings: Settings, *, i_understand: bool, allow_production: bool, allow_test_database: bool
) -> str | None:
    """Return why the command must not run here, or None."""
    if not i_understand:
        return "this publishes posts in members' names: pass --i-understand"
    name = make_url(settings.database_url.get_secret_value()).database or ""
    if (name.endswith("_test") or name == TEMPLATE_DATABASE) and not allow_test_database:
        return f"refusing the test database {name!r}"
    if settings.is_production and not allow_production:
        return "APP_ENV is production: pass --allow-production"
    return None


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli.publish_missing_posts",
        description="Publish the post of every basira made public or placed on the atlas "
        "before decision 68.",
    )
    parser.add_argument("--i-understand", action="store_true", dest="understood")
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="count, publish nothing")
    return parser.parse_args(argv)


async def execute(
    args: argparse.Namespace,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    *,
    allow_test_database: bool = False,
) -> int:
    """Run what `args` ask; return the exit code."""
    refused = check_allowed(
        settings,
        i_understand=args.understood,
        allow_production=args.allow_production,
        allow_test_database=allow_test_database,
    )
    if refused is not None:
        sys.stderr.write(f"{refused}\n")
        return 1
    try:
        async with (session_factory or get_sessionmaker())() as db:
            report = await publish_missing(
                db, settings, build_photo_store(settings), dry_run=args.dry_run
            )
    except (SQLAlchemyError, OSError) as error:
        sys.stderr.write(f"Cannot reach the database ({type(error).__name__}). Is it migrated?\n")
        return 1
    finally:
        if session_factory is None:
            await dispose_engine()
    for line in report.lines():
        sys.stdout.write(f"{line}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; return the process exit code."""
    args = _arguments(argv)
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return asyncio.run(execute(args, settings))


if __name__ == "__main__":
    raise SystemExit(main())
