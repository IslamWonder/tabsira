"""Refreshing the imported mock insights from a newer file: rewritten in place, or removed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.cli import import_mock
from src.cli.import_mock import MockImportError, refresh
from src.cli.mock_drop import DependentRowsError
from src.models import (
    Comment,
    Insight,
    InsightPublication,
    MapEntry,
    Post,
    PostReaction,
    ReactionKind,
    Scan,
    User,
)
from src.models.timeseries import EvidenceExposure
from src.models.world import Treasure, WorldReveal
from tests.test_import_mock import (  # noqa: F401  (fixtures)
    args,
    body,
    document,
    run,
    settings,
    world,
)

NEW_TITLE = "ماء صافٍ"


def parsed(data: dict[str, Any]) -> import_mock.MockFile:
    return import_mock.parse(json.dumps(data).encode())


def image(data: dict[str, Any], photo: int) -> dict[str, Any]:
    return next(i for i in data["images"] if i["placepix_id"] == photo)


def newer() -> dict[str, Any]:
    """The test file after photo 12 was run again (another hadith, title and step) and photo 16 found nothing."""
    data = document()
    image(data, 12)["insight"] = body(
        title=NEW_TITLE,
        hadith={"collection": "bukhari", "number": "8", "matched_on": "الإسلام"},
        small_step={"text": "تأمل الماء دقيقة", "kind": "reflection"},
    )
    image(data, 16)["insight"] = None
    next(p for p in data["posts"] if p["ref"] == "p1")["reflection"] = "تأمل جديد"
    return data


async def count(db: AsyncSession, model: Any, *conditions: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def of_photo(photo: int) -> Any:
    return Insight.photo_key.like(f"https://placepix.net/id/{photo}/%")


async def test_a_changed_photo_rewrites_its_insights_in_place_and_keeps_their_posts(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await run(db_session, settings, document())
    before = {
        i.id: i.created_at for i in await db_session.scalars(select(Insight).where(of_photo(12)))
    }
    post = await db_session.scalar(select(Post).where(Post.reflection == "تأمل قصير"))
    assert post is not None
    reactions = await count(db_session, PostReaction, PostReaction.post_id == post.id)
    comments = await count(db_session, Comment, Comment.post_id == post.id)

    report = await refresh(db_session, parsed(newer()), also_dependent_rows=False)

    assert report.refreshed == 2
    assert report.reflections == 1
    assert report.dropped.insights == 4
    rewritten = (await db_session.scalars(select(Insight).where(of_photo(12)))).all()
    assert {i.id: i.created_at for i in rewritten} == before
    assert {(i.title, i.hadith_collection, i.hadith_number) for i in rewritten} == {
        (NEW_TITLE, "bukhari", "8")
    }
    await db_session.refresh(post)
    publication = await db_session.scalar(
        select(InsightPublication).where(InsightPublication.id == post.publication_id)
    )
    assert publication is not None
    assert publication.title == NEW_TITLE
    assert publication.hadith_refs == [{"collection": "bukhari", "number": "8"}]
    assert publication.step_text == "تأمل الماء دقيقة"
    assert post.reflection == "تأمل جديد"
    assert await count(db_session, PostReaction, PostReaction.post_id == post.id) == reactions
    assert await count(db_session, Comment, Comment.post_id == post.id) == comments


async def test_a_completed_insight_has_its_world_written_again_from_the_new_texts(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await run(db_session, settings, document())
    done = await db_session.scalar(
        select(Insight).where(of_photo(12), Insight.completed_at.is_not(None))
    )
    assert done is not None

    await refresh(db_session, parsed(newer()))

    exposures = (
        await db_session.scalars(
            select(EvidenceExposure).where(EvidenceExposure.insight_id == done.id)
        )
    ).all()
    # The completion's record is written again from the new texts: the old hadith is gone from it.
    assert len(exposures) == 1
    assert exposures[0].hadith_number != "1"
    assert await count(db_session, WorldReveal, WorldReveal.insight_id == done.id) <= 1
    treasures = (
        await db_session.scalars(select(Treasure).where(Treasure.insight_id == done.id))
    ).all()
    assert all(t.hadith_number in (None, "8") for t in treasures)


async def test_a_second_refresh_and_a_refresh_with_the_same_file_change_nothing(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await run(db_session, settings, document())
    same = await refresh(db_session, parsed(document()))
    assert (same.refreshed, same.reflections, same.dropped.insights) == (0, 0, 0)
    assert same.unchanged > 0

    await refresh(db_session, parsed(newer()))
    again = await refresh(db_session, parsed(newer()))

    assert (again.refreshed, again.reflections, again.dropped.insights) == (0, 0, 0)


async def test_insights_never_imported_are_counted_and_left_to_the_import(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    report = await refresh(db_session, parsed(newer()))

    assert report.not_imported == len(document()["insights"])
    assert await count(db_session, Insight) == 0


async def test_a_photo_whose_evidence_left_the_store_is_left_as_it_was(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
):
    await run(db_session, settings, document())
    data = document()
    image(data, 12)["insight"] = body(
        hadith={"collection": "bukhari", "number": "9999", "matched_on": "x"}
    )

    report = await refresh(db_session, parsed(data))

    assert sorted(report.missing_evidence) == ["i1", "i5"]
    assert {
        i.hadith_number for i in await db_session.scalars(select(Insight).where(of_photo(12)))
    } == {"1"}


async def test_a_real_members_reaction_on_a_removed_insights_post_refuses_the_whole_refresh(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    make_user,
):
    await run(db_session, settings, document())
    real = await make_user("real@example.com", verified=True)
    gone = await db_session.scalar(select(Post).where(Post.reflection == "بلا صورة"))
    assert gone is not None
    db_session.add(PostReaction(post_id=gone.id, user_id=real.id, kind=ReactionKind.BENEFITED))
    await db_session.flush()

    with pytest.raises(DependentRowsError, match="reactions 1"):
        await refresh(db_session, parsed(newer()))

    report = await refresh(db_session, parsed(newer()), also_dependent_rows=True)
    assert report.dropped.dependents == {"reactions": 1}
    assert await db_session.get(User, real.id) is not None


async def test_a_file_that_fails_the_scripture_guard_refreshes_nothing(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    monkeypatch,
):
    await run(db_session, settings, document())

    async def refused(*_: object) -> None:
        raise MockImportError("scripture")

    monkeypatch.setattr(import_mock, "check_scripture_guard", refused)
    with pytest.raises(MockImportError):
        await refresh(db_session, parsed(newer()))
    assert {i.title for i in await db_session.scalars(select(Insight).where(of_photo(12)))} != {
        NEW_TITLE
    }


def test_the_refresh_takes_a_file_and_the_dependent_rows_flag():
    chosen = args("f.json", "--refresh-insights", "--i-understand", "--also-dependent-rows")
    assert chosen.refresh and chosen.also_dependent_rows
    for bad in (
        ["--refresh-insights"],
        ["--clean", "--refresh-insights"],
        ["f.json", "--also-dependent-rows"],
    ):
        with pytest.raises(SystemExit):
            args(*bad)


async def test_execute_refuses_then_refreshes_and_reports(
    db_session,
    settings,  # noqa: F811
    world,  # noqa: F811
    make_user,
    tmp_path,
    capsys,
):
    await run(db_session, settings, document())
    real = await make_user("real@example.com", verified=True)
    gone = await db_session.scalar(select(Post).where(Post.reflection == "بلا صورة"))
    assert gone is not None
    db_session.add(PostReaction(post_id=gone.id, user_id=real.id, kind=ReactionKind.BENEFITED))
    await db_session.flush()
    path = tmp_path / "newer.json"
    path.write_text(json.dumps(newer()), encoding="utf-8")
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    refused = await import_mock.execute(
        args(str(path), "--refresh-insights", "--i-understand"),
        settings,
        factory,
        allow_test_database=True,
    )
    assert refused == 1
    assert "--also-dependent-rows" in capsys.readouterr().err
    done = await import_mock.execute(
        args(str(path), "--refresh-insights", "--i-understand", "--also-dependent-rows"),
        settings,
        factory,
        allow_test_database=True,
    )
    assert done == 0
    out = capsys.readouterr().out
    assert "insights rewritten 2" in out
    assert "removed 4 insights whose photo has no insight any more" in out
    assert "removed 1 reactions of other members" in out
    assert await count(db_session, Scan) > 0
    assert await count(db_session, MapEntry) > 0
