"""What the engine may know of a learner, and what a completion records."""

from __future__ import annotations

from sqlalchemy import select

from src import clock
from src.models import EvidenceExposure, Guest, LearnerUnitState, Profile
from src.owner import Owner
from src.pipeline.engine import HadithRef, LearnerContext, QuranRef
from src.services import learner_service
from tests.scans.conftest import make_account

PATH = "tabsira-masar-1.0"


async def test_a_guest_gets_neutral_defaults_and_its_own_history(store):
    owner = Owner(guest_key="a" * 64)
    async with store() as db:
        db.add(Guest(key=owner.guest_key))
        await db.flush()
        for surah, ayah, collection, number in (
            (30, 50, "bukhari", "1032"),
            (30, 50, None, None),
            (None, None, "bukhari", "1032"),
        ):
            db.add(
                learner_service.exposure(
                    owner,
                    kind="completed",
                    at=clock.utcnow(),
                    insight_id=None,
                    quran=QuranRef(surah=surah, ayah=ayah) if surah else None,
                    hadith=HadithRef(collection=collection, number=number) if collection else None,
                    concept="الإحياء",
                    unit_id="T01_06",
                )
            )
        await learner_service.record_completion(
            db, owner, unit_id="T01_06", path_version=PATH, at=clock.utcnow()
        )
        await learner_service.record_completion(
            db, owner, unit_id="T01_06", path_version=PATH, at=clock.utcnow()
        )
        await learner_service.record_completion(
            db, owner, unit_id=None, path_version=PATH, at=clock.utcnow()
        )

        context = await learner_service.learner_context(db, owner)
        state = (await db.scalars(select(LearnerUnitState))).one()

    assert context.religious_background == "unknown"
    assert context.personalization_enabled
    assert context.seen_quran == [QuranRef(surah=30, ayah=50)]
    assert context.seen_hadith == [HadithRef(collection="bukhari", number="1032")]
    assert context.completed_units == ["T01_06"]
    assert state.completed_count == 2
    assert await learner_service.memory_enabled(db, owner)


async def test_a_shown_text_is_recorded_once_per_insight_and_counts_as_seen(store):
    owner = Owner(guest_key="b" * 64)
    verse = QuranRef(surah=30, ayah=50)
    hadith = HadithRef(collection="bukhari", number="1032")
    async with store() as db:
        db.add(Guest(key=owner.guest_key))
        await db.flush()

        def show(insight_id: int, quran: QuranRef | None, found: HadithRef | None):
            return learner_service.record_shown(
                db,
                owner,
                insight_id=insight_id,
                at=clock.utcnow(),
                quran=quran,
                hadith=found,
                concept="الإحياء",
                unit_id="T01_06",
            )

        first = await show(1, verse, None)
        again = await show(1, verse, None)
        later = await show(1, verse, hadith)
        complete = await show(1, verse, hadith)
        nothing = await show(1, None, None)
        other_insight = await show(2, verse, hadith)
        rows = (await db.scalars(select(EvidenceExposure).order_by(EvidenceExposure.id))).all()
        context = await learner_service.learner_context(db, owner)

    assert (first, again, later, complete, nothing, other_insight) == (
        True,
        False,
        True,
        False,
        False,
        True,
    )
    assert [(r.kind, r.insight_id, r.quran_ayah, r.hadith_number) for r in rows] == [
        ("shown", 1, 50, None),
        ("shown", 1, None, "1032"),
        ("shown", 2, 50, "1032"),
    ]
    assert (context.seen_quran, context.seen_hadith) == ([verse], [hadith])
    assert (learner_service.KIND_COMPLETED, learner_service.KIND_TREASURE) == (
        "completed",
        "treasure",
    )


async def test_an_account_shares_its_profile_only_while_personalization_is_on(store):
    user = await make_account(store)
    owner = Owner(user_id=user.id)
    async with store() as db:
        profile = await db.get(Profile, user.id)
        profile.goals = ["reflection"]
        profile.knowledge_level = "general"
        profile.age_range = "25_39"
        profile.religious_background = "non_muslim"
        profile.gender = "woman"
        await db.flush()
        db.add(
            learner_service.exposure(
                owner,
                kind="completed",
                at=clock.utcnow(),
                insight_id=None,
                quran=QuranRef(surah=30, ayah=50),
                hadith=None,
                concept="x" * 100,
                unit_id=None,
            )
        )
        await learner_service.record_completion(
            db, owner, unit_id="T12_02", path_version=PATH, at=clock.utcnow()
        )
        shared = await learner_service.learner_context(db, owner)
        chat = await learner_service.profile_context(db, user.id)

        profile.personalization_enabled = False
        profile.memory_enabled = False
        await db.flush()
        private = await learner_service.learner_context(db, owner)
        chat_private = await learner_service.profile_context(db, user.id)
        guest = await learner_service.profile_context(db, None)
        assert not await learner_service.memory_enabled(db, owner)
        concept = (await db.scalars(select(EvidenceExposure.concept))).one()

    assert (shared.goals, shared.knowledge_level, shared.age_range) == (
        ["reflection"],
        "general",
        "25_39",
    )
    assert (shared.religious_background, shared.gender) == ("non_muslim", "woman")
    # The chat reads the same declared fields, never the history.
    assert chat == shared.model_copy(update={"completed_units": [], "seen_quran": []})
    assert chat_private == private == LearnerContext(personalization_enabled=False)
    assert guest == LearnerContext()
    assert shared.completed_units == ["T12_02"]
    assert private == LearnerContext(personalization_enabled=False)
    assert concept == "x" * 80
