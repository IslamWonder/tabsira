"""
The rain tutorial (v2 §4): a prepared, reviewed example, hydrated from the store, never waiting on AI.

The scene is data (`data/tutorial/rain-<version>.json`) with its two insights:
«الحياة في قطرة» (Ar-Rum 30:50, al-Bukhari 1032) and «الغرس الذي يتعدّاك»
(al-An'am 6:99, al-Bukhari 2320), cited by reference only. Every text of
scripture is read from the store as the read API shows it. A hadith shows only
once an editor has recorded its dorar.net ruling and it reads صحيح or حسن; until
then the insight shows its verse alone and says the hadith waits for
verification. The whole answer is labelled «مثال موثّق مُعدّ». A learner who
completes one keeps a copy of it, so «تمّ», the world and the chat work on it
exactly as on an insight of their own photo.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.errors import AppError, ErrorCode
from src.messages import messages_for
from src.models import Insight, InsightOrigin
from src.owner import Owner
from src.schemas.insight import InsightHadith, InsightQuran, InsightWhyOut
from src.schemas.tutorial import TutorialImageOut, TutorialInsightOut, TutorialOut
from src.services.content import Tutorial, TutorialInsight
from src.services.insight_view import evidence, evidence_why, explanation_out, step_out

PREPARED = "prepared"


async def describe(db: AsyncSession, tutorial: Tutorial) -> TutorialOut:
    """Return the tutorial with its scripture read from the store."""
    return TutorialOut(
        scene=tutorial.scene,
        version=tutorial.version,
        title=tutorial.title,
        label=messages_for().prepared_example,
        status="prepared",
        image=TutorialImageOut.model_validate(tutorial.image.model_dump()),
        insights=[await _insight(db, insight) for insight in tutorial.insights],
        disclosure=messages_for().ai_disclosure,
    )


async def _insight(db: AsyncSession, insight: TutorialInsight) -> TutorialInsightOut:
    hadith_ref = (insight.hadith.collection, insight.hadith.number) if insight.hadith else None
    verse, hadith, awaiting = await evidence(
        db, (insight.quran.surah, insight.quran.ayah), hadith_ref
    )
    if verse is None:
        raise AppError(
            ErrorCode.ASSET_MISSING,
            "The verses of the tutorial are not in the store; run make data.",
            status_code=503,
        )
    quran_why = insight.quran.model_dump(include={"relation", "matched_on"}, mode="json")
    hadith_why = (
        insight.hadith.model_dump(include={"relation", "matched_on"}, mode="json")
        if insight.hadith
        else None
    )
    return TutorialInsightOut(
        slug=insight.slug,
        title=insight.title,
        glimpse=insight.glimpse,
        anchor=insight.anchor,
        relation=insight.relation,
        relation_label=messages_for().relation_labels[insight.relation.value],
        quran=InsightQuran(tag=messages_for().quran_tag, verse=verse, why=evidence_why(quran_why)),
        hadith=InsightHadith(
            tag=messages_for().sunnah_tag, hadith=hadith, why=evidence_why(hadith_why)
        )
        if hadith
        else None,
        hadith_status="shown" if hadith else "awaiting_verification" if awaiting else "none",
        notice=messages_for().hadith_awaits_verification if awaiting else None,
        pair_complete=hadith is not None,
        explanation_tag=messages_for().explanation_tag,
        explanation=explanation_out(
            [part.model_dump(mode="json") for part in insight.explanation], verse, hadith
        ),
        why=InsightWhyOut(
            visible_clues=insight.why.visible_clues,
            concept=insight.why.concept,
            limits=insight.why.limits,
            personalised_because=None,
        ),
        small_step=step_out(
            insight.small_step.model_dump(mode="json") if insight.small_step else None,
            verse,
            hadith,
        ),
        learning_unit_id=insight.learning_unit_id,
    )


async def keep(db: AsyncSession, owner: Owner, tutorial: Tutorial, slug: str) -> Insight:
    """Return the owner's copy of a tutorial insight, made on first use."""
    prepared = tutorial.insight(slug)
    if prepared is None:
        raise AppError(ErrorCode.NOT_FOUND, "No such tutorial insight.", status_code=404)
    column = Insight.user_id if owner.user_id is not None else Insight.guest_key
    await db.execute(
        insert(Insight)
        .values(
            **owner.columns(),
            origin=InsightOrigin.TUTORIAL,
            tutorial_scene=tutorial.key,
            tutorial_slug=slug,
            engine=PREPARED,
            title=prepared.title,
            glimpse=prepared.glimpse,
            anchor=prepared.anchor.model_dump(),
            relation=prepared.relation.value,
            quran_surah=prepared.quran.surah,
            quran_ayah=prepared.quran.ayah,
            quran_evidence=prepared.quran.model_dump(
                include={"relation", "matched_on"}, mode="json"
            ),
            hadith_collection=prepared.hadith.collection if prepared.hadith else None,
            hadith_number=prepared.hadith.number if prepared.hadith else None,
            hadith_evidence=prepared.hadith.model_dump(
                include={"relation", "matched_on"}, mode="json"
            )
            if prepared.hadith
            else None,
            explanation=[part.model_dump(mode="json") for part in prepared.explanation],
            why=prepared.why.model_dump(mode="json"),
            small_step=prepared.small_step.model_dump(mode="json") if prepared.small_step else None,
            learning_unit_id=prepared.learning_unit_id,
            learning_path_version=prepared.learning_path_version,
        )
        .on_conflict_do_nothing(
            index_elements=[column, Insight.tutorial_scene, Insight.tutorial_slug],
            index_where=column.is_not(None) & Insight.tutorial_slug.is_not(None),
        )
    )
    kept = (
        await db.scalars(
            select(Insight).where(
                owner.where(Insight),
                Insight.tutorial_scene == tutorial.key,
                Insight.tutorial_slug == slug,
            )
        )
    ).one()
    await db.commit()
    return kept
