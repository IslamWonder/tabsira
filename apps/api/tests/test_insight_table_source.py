"""The social network's insight source over the insights table: whose insight, and what a post copies."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scan import Guest
from src.models.social import EXPLANATION_MAX
from src.owner import Owner
from src.services.insight_source import HadithRef, QuranRef
from src.services.insight_table_source import InsightTableSource, explanation_excerpt, snapshot_of
from tests.scans.builders import insight_row, scan_row


async def _insight(db: AsyncSession, owner: Owner, **values: object):
    scan = scan_row(owner, sensitive=bool(values.pop("sensitive", False)))
    db.add(scan)
    await db.flush()
    insight = insight_row(owner, scan_id=scan.id, **values)
    db.add(insight)
    await db.flush()
    return insight


async def test_the_owner_s_pipeline_insight_is_copied_by_reference(db_session, make_user):
    user = await make_user("author@example.com")
    insight = await _insight(db_session, Owner(user_id=user.id), entity_ids=["rain", "plant"])

    snapshot = await InsightTableSource().load_for_publishing(db_session, insight.id, user.id)

    assert snapshot is not None
    assert (snapshot.insight_id, snapshot.owner_id, snapshot.verified) == (
        insight.id,
        user.id,
        True,
    )
    assert (snapshot.title, snapshot.glimpse, snapshot.relation_type) == (
        "الحياة في قطرة",
        "الماء سبب للحياة",
        "direct",
    )
    assert snapshot.quran_refs == (QuranRef(30, 50),)
    assert snapshot.hadith_refs == (HadithRef("bukhari", "1032"),)
    assert snapshot.explanation_excerpt == "قطرات على ورق نبتة."
    assert snapshot.step_text == "احفظ الدعاء الوارد في الحديث."
    assert snapshot.concepts == ("rain", "plant")
    # No photo was kept with this insight: nothing is offered for publishing.
    assert (snapshot.photo_ref, snapshot.photo_consent, snapshot.scene_sensitive) == (
        None,
        False,
        False,
    )


async def test_a_post_of_an_insight_written_with_the_profile_copies_no_explanation_or_step(
    db_session, make_user
):
    user = await make_user("author@example.com")
    insight = await _insight(
        db_session,
        Owner(user_id=user.id),
        why={
            "visible_clues": [],
            "concept": "x",
            "limits": [],
            "personalised_because": "اخترنا مدخلًا قريبًا لأن هذه من أولى بصائرك.",
        },
    )

    snapshot = await InsightTableSource().load_for_publishing(db_session, insight.id, user.id)

    assert snapshot is not None
    assert (snapshot.explanation_excerpt, snapshot.step_text) == ("", None)
    assert snapshot.title == "الحياة في قطرة"


async def test_a_kept_photo_is_offered_by_its_private_key_and_never_its_public_one(
    db_session, make_user
):
    user = await make_user("author@example.com")
    private, public = "private/" + "a" * 32 + ".jpg", "public/" + "b" * 32 + ".jpg"
    insight = await _insight(
        db_session, Owner(user_id=user.id), photo_key=private, photo_public_key=public
    )

    snapshot = await InsightTableSource().load_for_publishing(db_session, insight.id, user.id)

    assert snapshot is not None
    assert (snapshot.photo_ref, snapshot.photo_consent) == (private, True)
    assert public not in str(snapshot)


async def test_another_account_s_insight_and_a_missing_one_answer_the_same(db_session, make_user):
    author = await make_user("author@example.com")
    other = await make_user("other@example.com")
    insight = await _insight(db_session, Owner(user_id=author.id))
    source = InsightTableSource()

    assert await source.load_for_publishing(db_session, insight.id, other.id) is None
    assert await source.load_for_publishing(db_session, insight.id + 1, author.id) is None


async def test_a_guest_s_insight_is_nobody_s_to_publish(db_session, make_user):
    user = await make_user("author@example.com")
    db_session.add(Guest(key="g" * 64))
    await db_session.flush()
    insight = await _insight(db_session, Owner(guest_key="g" * 64))

    assert await InsightTableSource().load_for_publishing(db_session, insight.id, user.id) is None
    with pytest.raises(ValueError, match="account"):
        snapshot_of(insight, None)


@pytest.mark.parametrize("kind", ["demo", "prepared"])
async def test_a_simulated_or_prepared_insight_is_not_verified(db_session, make_user, kind):
    user = await make_user("author@example.com")
    insight = await _insight(db_session, Owner(user_id=user.id), engine=kind)

    snapshot = await InsightTableSource().load_for_publishing(db_session, insight.id, user.id)

    assert snapshot is not None
    assert snapshot.verified is False


async def test_a_sensitive_scene_and_missing_pieces_are_reported_as_they_are(db_session, make_user):
    user = await make_user("author@example.com")
    insight = await _insight(
        db_session,
        Owner(user_id=user.id),
        sensitive=True,
        hadith_collection=None,
        hadith_number=None,
        hadith_evidence=None,
        small_step=None,
    )

    snapshot = await InsightTableSource().load_for_publishing(db_session, insight.id, user.id)

    assert snapshot is not None
    assert snapshot.scene_sensitive is True
    assert snapshot.hadith_refs == ()
    assert snapshot.step_text is None


def test_an_explanation_is_joined_in_order_and_cut_at_a_sentence_when_too_long():
    parts = [{"section": "seen", "text": "  أولى.  "}, {"section": "value", "text": "ثانية."}]
    assert explanation_excerpt(parts) == "أولى. ثانية."

    sentence = "جملة قصيرة. "
    long = [{"section": "life", "text": sentence * 200}]
    excerpt = explanation_excerpt(long)
    assert len(excerpt) <= EXPLANATION_MAX
    assert excerpt.endswith(".…")

    # No sentence end in the first half: the cut falls on a space; no space at all: on the limit.
    words = " ".join(["كلمة"] * 400)
    assert explanation_excerpt([{"text": words}]).endswith("كلمة…")
    assert len(explanation_excerpt([{"text": "ك" * 2000}])) == EXPLANATION_MAX


def test_the_bare_snapshot_has_no_scan():
    insight = insight_row(Owner(user_id=uuid.uuid4()), explanation=[])
    insight.id = 7
    snapshot = snapshot_of(insight, None)
    assert (snapshot.scene_sensitive, snapshot.explanation_excerpt) == (False, "")
