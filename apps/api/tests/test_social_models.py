"""The social tables, as built from the models: constraints, immutability and the moderation log."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from alembic import op
from src.models import (
    Block,
    Bookmark,
    Comment,
    CommentStatus,
    Follow,
    InsightPublication,
    ModerationAction,
    ModerationActionKind,
    ModerationSource,
    ModerationTarget,
    Post,
    PostReaction,
    PostStatus,
    PostVisibility,
    ReactionKind,
    RemovalSource,
    Report,
    ReportReason,
    ReportStatus,
    ReportTarget,
    User,
)
from src.models import moderation as moderation_model
from src.models.public_id import create_sequence_sql
from src.models.social import PUBLICATION_IMMUTABLE_STATEMENTS
from src.models.user import HANDLE_PATTERN
from tests.helpers import any_id

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION = next((API_DIR / "alembic" / "versions").glob("*_create_social_network_tables.py"))


async def user(db_session, email="a@example.com", **columns):
    row = User(email=email, display_name="A", **columns)
    db_session.add(row)
    await db_session.flush()
    return row


async def publication(db_session, author, **columns):
    values = {
        "author_id": author.id,
        "insight_id": any_id(),
        "insight_version": 1,
        "title": "t",
        "glimpse": "g",
        "relation_type": "direct",
        "quran_refs": [{"surah": 112, "ayah": 1}],
        "hadith_refs": [],
        "explanation_excerpt": "e",
        **columns,
    }
    row = InsightPublication(**values)
    db_session.add(row)
    await db_session.flush()
    return row


async def post(db_session, author, **columns):
    row = Post(author_id=author.id, **columns)
    db_session.add(row)
    await db_session.flush()
    return row


# ─── Handles ──────────────────────────────────────────────────────────────────


async def test_a_user_starts_with_no_public_identity(db_session):
    row = await user(db_session)

    assert (row.handle, row.public_name) == (None, None)


async def test_a_handle_is_unique_whatever_its_case(db_session):
    await user(db_session, "a@example.com", handle="Basira_1")

    with pytest.raises(IntegrityError, match="uq_users_handle_lower"):
        async with db_session.begin_nested():
            db_session.add(User(email="b@example.com", display_name="B", handle="basira_1"))
            await db_session.flush()


async def test_many_users_may_have_no_handle(db_session):
    await user(db_session, "a@example.com")
    await user(db_session, "b@example.com")


@pytest.mark.parametrize("handle", ["محمد_1", "abc", "a" * 30, "تبصرة", "Abc_123"])
async def test_the_database_accepts_a_well_formed_handle(db_session, handle):
    await user(db_session, handle=handle)


@pytest.mark.parametrize(
    "handle",
    ["ab", "1abc", "_abc", "a b", "a-b", "مَحمد", "محـمد", "a@b", "ab‌c", ""],
)
async def test_the_database_refuses_a_malformed_handle(db_session, handle):
    with pytest.raises(IntegrityError, match="ck_users_handle_format"):
        async with db_session.begin_nested():
            db_session.add(User(email="x@example.com", display_name="X", handle=handle))
            await db_session.flush()


# ─── Follows and blocks ───────────────────────────────────────────────────────


async def test_a_follow_is_one_per_pair_and_never_to_oneself(db_session):
    one, two = await user(db_session, "1@example.com"), await user(db_session, "2@example.com")
    db_session.add(Follow(follower_id=one.id, followee_id=two.id))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="pk_follows"):
        async with db_session.begin_nested():
            db_session.add(Follow(follower_id=one.id, followee_id=two.id))
            await db_session.flush()
    with pytest.raises(IntegrityError, match="ck_follows_no_self_follow"):
        async with db_session.begin_nested():
            db_session.add(Follow(follower_id=one.id, followee_id=one.id))
            await db_session.flush()
    # The reverse pair is another follow.
    db_session.add(Follow(follower_id=two.id, followee_id=one.id))
    await db_session.flush()


async def test_a_block_is_one_per_pair_and_never_on_oneself(db_session):
    one, two = await user(db_session, "1@example.com"), await user(db_session, "2@example.com")
    db_session.add(Block(blocker_id=one.id, blocked_id=two.id))
    await db_session.flush()

    with pytest.raises(IntegrityError, match="pk_blocks"):
        async with db_session.begin_nested():
            db_session.add(Block(blocker_id=one.id, blocked_id=two.id))
            await db_session.flush()
    with pytest.raises(IntegrityError, match="ck_blocks_no_self_block"):
        async with db_session.begin_nested():
            db_session.add(Block(blocker_id=two.id, blocked_id=two.id))
            await db_session.flush()


# ─── Publications ─────────────────────────────────────────────────────────────


async def test_a_publication_keeps_references_and_never_scripture_text(db_session):
    author = await user(db_session)

    row = await publication(
        db_session,
        author,
        quran_refs=[{"surah": 2, "ayah": 255}],
        hadith_refs=[{"collection": "bukhari", "number": "1"}],
        concepts=["water"],
    )

    # A public id: time-ordered, 64 bits, not a row count.
    assert row.id > 2**40
    assert row.concepts == ["water"]
    assert row.photo_ref is None
    assert {column.name for column in InsightPublication.__table__.columns} == {
        "id",
        "author_id",
        "insight_id",
        "insight_version",
        "title",
        "glimpse",
        "relation_type",
        "concepts",
        "quran_refs",
        "hadith_refs",
        "explanation_excerpt",
        "step_text",
        "photo_ref",
        "created_at",
    }


async def test_a_publication_needs_evidence_in_the_right_shape(db_session):
    author = await user(db_session)

    for columns in (
        {"quran_refs": [], "hadith_refs": []},
        {"quran_refs": {"surah": 1}},
        {"hadith_refs": "x"},
    ):
        with pytest.raises(IntegrityError, match="ck_insight_publications_has_evidence"):
            async with db_session.begin_nested():
                await publication(db_session, author, **columns)


async def test_a_publication_can_be_deleted_but_never_edited(db_session):
    author = await user(db_session)
    row = await publication(db_session, author)

    with pytest.raises(DBAPIError, match="insight publications are immutable"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE app.insight_publications SET title = 'new'"))

    await db_session.delete(row)
    await db_session.flush()
    assert await db_session.scalar(select(InsightPublication)) is None


# ─── Posts and what hangs on them ─────────────────────────────────────────────


async def test_a_new_post_is_a_public_draft_with_no_counters(db_session):
    author = await user(db_session)

    row = await post(db_session, author)

    assert row.status is PostStatus.DRAFT
    assert row.visibility is PostVisibility.PUBLIC
    assert row.reflection_looks_like_scripture is False
    assert row.published_at is None
    assert row.updated_at is not None
    assert {"reaction_count", "comment_count", "reactions", "comments"}.isdisjoint(
        {column.name for column in Post.__table__.columns}
    )


async def test_a_published_post_has_a_time_and_a_removed_one_a_source(db_session):
    author = await user(db_session)

    with pytest.raises(IntegrityError, match="ck_posts_published_has_time"):
        async with db_session.begin_nested():
            await post(db_session, author, status=PostStatus.PUBLISHED)
    with pytest.raises(IntegrityError, match="ck_posts_removed_has_source"):
        async with db_session.begin_nested():
            await post(db_session, author, status=PostStatus.REMOVED)
    await post(
        db_session, author, status=PostStatus.REMOVED, removal_source=RemovalSource.MODERATOR
    )


@pytest.mark.parametrize("column", ["status", "visibility"])
async def test_the_database_refuses_a_post_state_it_does_not_know(db_session, column):
    author = await user(db_session)
    await post(db_session, author)

    with pytest.raises(IntegrityError, match=f"ck_posts_{column}"):
        async with db_session.begin_nested():
            await db_session.execute(text(f"UPDATE app.posts SET {column} = 'bogus'"))  # noqa: S608


async def test_a_publication_backs_one_post_and_a_deleted_one_leaves_the_post_standing(
    db_session,
):
    author = await user(db_session)
    pub = await publication(db_session, author)
    row = await post(db_session, author, publication_id=pub.id)

    with pytest.raises(IntegrityError, match="uq_posts_publication_id"):
        async with db_session.begin_nested():
            await post(db_session, author, publication_id=pub.id)
    await db_session.delete(pub)
    await db_session.flush()
    await db_session.refresh(row)

    assert row.publication_id is None


async def test_a_reaction_of_a_kind_and_a_bookmark_are_one_per_account_and_post(db_session):
    author = await user(db_session)
    row = await post(db_session, author)
    db_session.add_all(
        [
            PostReaction(post_id=row.id, user_id=author.id, kind=ReactionKind.JAZAK),
            Bookmark(user_id=author.id, post_id=row.id),
        ]
    )
    await db_session.flush()

    with pytest.raises(IntegrityError, match="pk_post_reactions"):
        async with db_session.begin_nested():
            db_session.add(PostReaction(post_id=row.id, user_id=author.id, kind=ReactionKind.JAZAK))
            await db_session.flush()
    # The other kind is another reaction.
    db_session.add(PostReaction(post_id=row.id, user_id=author.id, kind=ReactionKind.BENEFITED))
    await db_session.flush()
    with pytest.raises(IntegrityError, match="pk_bookmarks"):
        async with db_session.begin_nested():
            db_session.add(Bookmark(user_id=author.id, post_id=row.id))
            await db_session.flush()


async def test_a_reply_is_removed_with_its_parent_and_a_comment_starts_in_review(db_session):
    author = await user(db_session)
    row = await post(db_session, author)
    top = Comment(post_id=row.id, author_id=author.id, body="top")
    db_session.add(top)
    await db_session.flush()
    reply = Comment(post_id=row.id, author_id=author.id, body="reply", parent_id=top.id)
    db_session.add(reply)
    await db_session.flush()

    assert top.status is CommentStatus.PENDING_REVIEW

    await db_session.delete(top)
    await db_session.flush()
    assert await db_session.scalar(select(Comment).where(Comment.id == reply.id)) is None


async def test_a_report_is_one_per_reporter_and_target_and_outlives_its_target(db_session):
    reporter = await user(db_session)
    target = any_id()
    db_session.add(
        Report(
            reporter_id=reporter.id,
            target_type=ReportTarget.POST,
            target_id=target,
            reason=ReportReason.WRONG_PLACE,
        )
    )
    await db_session.flush()

    with pytest.raises(IntegrityError, match="uq_reports_reporter_target"):
        async with db_session.begin_nested():
            db_session.add(
                Report(
                    reporter_id=reporter.id,
                    target_type=ReportTarget.POST,
                    target_id=target,
                    reason=ReportReason.SPAM,
                )
            )
            await db_session.flush()
    stored = await db_session.scalar(select(Report))
    assert stored.status is ReportStatus.OPEN
    assert {reason.value for reason in ReportReason} == {
        "abuse",
        "spam",
        "false_religious_claim",
        "unauthorised_photo",
        "wrong_place",
        "private_information",
        "other",
    }


async def test_deleting_a_user_removes_everything_they_published_and_did(db_session):
    author, reader = (
        await user(db_session, "1@example.com"),
        await user(db_session, "2@example.com"),
    )
    pub = await publication(db_session, author)
    row = await post(db_session, author, publication_id=pub.id)
    comment = Comment(post_id=row.id, author_id=reader.id, body="c")
    db_session.add_all(
        [
            Follow(follower_id=reader.id, followee_id=author.id),
            Block(blocker_id=author.id, blocked_id=reader.id),
            PostReaction(post_id=row.id, user_id=reader.id, kind=ReactionKind.BENEFITED),
            Bookmark(user_id=reader.id, post_id=row.id),
            comment,
            Report(
                reporter_id=reader.id,
                target_type=ReportTarget.POST,
                target_id=row.id,
                reason=ReportReason.OTHER,
            ),
        ]
    )
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": author.id})
    await db_session.execute(text("DELETE FROM app.users WHERE id = :id"), {"id": reader.id})

    for table in (
        "follows",
        "blocks",
        "insight_publications",
        "posts",
        "post_reactions",
        "bookmarks",
        "comments",
        "reports",
    ):
        count = (await db_session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one()  # noqa: S608
        assert count == 0, table


# ─── The moderation log ───────────────────────────────────────────────────────


async def log(db_session, **values):
    row = ModerationAction(
        target_type=values.pop("target_type", ModerationTarget.POST),
        target_id=values.pop("target_id", any_id()),
        action=values.pop("action", ModerationActionKind.HELD),
        source=values.pop("source", ModerationSource.GUARD),
        **values,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def scalar(db_session, sql, **params):
    return (await db_session.execute(text(sql), params)).scalar_one()


async def test_the_log_is_a_hypertable_partitioned_on_its_time_column(db_session):
    dimension = await scalar(
        db_session,
        "SELECT column_name FROM timescaledb_information.dimensions "
        "WHERE hypertable_schema = 'app' AND hypertable_name = 'moderation_actions'",
    )
    key = (
        await db_session.execute(
            text(
                """
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
                WHERE i.indrelid = 'app.moderation_actions'::regclass AND i.indisprimary
                """
            )
        )
    ).scalars()

    assert dimension == "at"
    assert set(key) == {"at", "id"}


async def test_the_default_retention_and_compression_policies_are_set(db_session):
    jobs = {
        row.proc_name: row.config
        for row in await db_session.execute(
            text(
                "SELECT proc_name, config FROM timescaledb_information.jobs "
                "WHERE hypertable_schema = 'app' AND hypertable_name = 'moderation_actions'"
            )
        )
    }

    assert jobs["policy_retention"]["drop_after"] == "730 days"
    assert jobs["policy_compression"]["compress_after"] == "30 days"


async def test_a_row_is_added_with_its_time_and_never_changed_or_deleted(db_session):
    row = await log(db_session, reason="guard_uncertain", details={"categories": ["hate"]})

    assert row.at is not None
    assert row.id >= 1
    for statement in (
        "UPDATE app.moderation_actions SET reason = 'x'",
        "DELETE FROM app.moderation_actions",
    ):
        with pytest.raises(IntegrityError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(statement))
    assert await scalar(db_session, "SELECT count(*) FROM app.moderation_actions") == 1


async def test_the_database_refuses_a_decision_it_does_not_know(db_session):
    with pytest.raises(IntegrityError, match="ck_moderation_actions_action"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO app.moderation_actions (target_type, target_id, action, source) "
                    "VALUES ('post', :id, 'erase', 'guard')"
                ),
                {"id": any_id()},
            )


async def test_the_policies_can_be_replaced_with_other_windows(db_session):
    for statement in moderation_model.policy_statements(retention_days=100, compress_after_days=10):
        await db_session.execute(text(statement))

    jobs = {
        row.proc_name: row.config
        for row in await db_session.execute(
            text(
                "SELECT proc_name, config FROM timescaledb_information.jobs "
                "WHERE hypertable_name = 'moderation_actions'"
            )
        )
    }
    assert jobs["policy_retention"]["drop_after"] == "100 days"
    assert jobs["policy_compression"]["compress_after"] == "10 days"


def squash(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def load_migration():
    spec = importlib.util.spec_from_file_location("social_migration", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_and_the_models_build_the_same_hypertable_and_triggers(monkeypatch):
    migration = load_migration()
    statements: list[str] = []
    monkeypatch.setattr(op, "f", lambda name: name, raising=False)
    for name in ("add_column", "create_table", "create_index", "create_check_constraint"):
        monkeypatch.setattr(op, name, lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(op, "execute", statements.append, raising=False)

    migration.upgrade()

    from_models = [
        *(create_sequence_sql(table) for table in migration.PUBLIC_ID_TABLES),
        *(squash(statement) for statement in PUBLICATION_IMMUTABLE_STATEMENTS),
        *(squash(statement) for statement in moderation_model.HYPERTABLE_STATEMENTS),
        *(
            squash(statement)
            for statement in moderation_model.policy_statements(730, 30)
            if "remove_" not in statement
        ),
    ]
    assert [squash(statement) for statement in statements] == from_models


def test_the_migration_writes_the_handle_format_and_the_evidence_rule_the_model_does():
    migration = load_migration()
    evidence = next(
        constraint
        for constraint in InsightPublication.__table__.constraints
        if constraint.name == "ck_insight_publications_has_evidence"
    )

    assert migration.HANDLE_PATTERN == HANDLE_PATTERN
    assert str(evidence.sqltext) == migration.EVIDENCE_CHECK
