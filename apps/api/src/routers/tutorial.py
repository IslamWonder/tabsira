"""The rain tutorial (v2 §4): «مثال موثّق مُعدّ», read from the store, never waiting on a provider."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from src.deps import DbDep, SettingsDep
from src.owner import WritingOwner
from src.scans.deps import KEEP_LIMITS, address_limit
from src.schemas.insight import InsightDetailOut
from src.schemas.tutorial import TutorialOut
from src.services import account_gate, insight_view, tutorial_service
from src.services.content import load_tutorial

router = APIRouter(prefix="/tutorial", tags=["tutorial"])


@router.get("/rain", summary="The prepared rain scene and its two insights")
async def rain(db: DbDep) -> TutorialOut:
    """
    Return the rain scene with «الحياة في قطرة» and «الغرس الذي يتعدّاك».

    The verses and the hadiths come from the store, each hadith as stored with
    no ruling displayed (decision 65).
    """
    return await tutorial_service.describe(db, load_tutorial())


@router.post(
    "/rain/insights/{slug}",
    summary="Keep a copy of a tutorial insight, to complete it and ask about it",
    dependencies=[Depends(address_limit(KEEP_LIMITS, "Too many requests. Try again later."))],
)
async def keep_rain_insight(
    slug: Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{1,63}$")],
    db: DbDep,
    settings: SettingsDep,
    owner: WritingOwner,
) -> InsightDetailOut:
    """
    Return the caller's copy of the insight (made once), labelled «مثال موثّق مُعدّ».

    An account that holds an insight of its own answers 403 `tutorial_closed` (decision 64).
    """
    await account_gate.require_tutorial_open(db, owner)
    kept = await tutorial_service.keep(db, owner, load_tutorial(), slug)
    return await insight_view.describe(db, settings, kept, owner)
