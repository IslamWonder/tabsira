"""
The sound of a scene, announced while the scan is still being prepared.

The sound of an entity is known as soon as the scene is matched to the ontology,
long before the insight is: the scan job announces it right after the scene is
understood, and the reader hears it while the evidence is searched. It is
heard around the photo only; the page fades it out before any verse shows.

No sound for a sensitive scene, nor for an entity the ontology blocks or wants
clarified first: a sound would presume what the scan does not.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.pipeline.insight.context import build_context
from src.pipeline.schemas import SceneAnalysis
from src.storage.base import InvalidKeyError, ObjectNotFoundError, StorageUnavailableError
from src.storage.sounds import SoundStore

# The storage is asked about this many entities at most, in the scene's order.
TRIED_ENTITIES = 3


def sound_path(entity_id: str) -> str:
    """Return the API path that serves an entity's sound."""
    return f"/sounds/ontology/{entity_id}"


async def candidate_entities(
    session: AsyncSession, scene: SceneAnalysis, *, focus_id: str | None, clarified: bool
) -> list[str]:
    """Return the ontology ids the scene's sound may come from, best first."""
    if scene.is_sensitive:
        return []
    context = await build_context(session, scene, clarified=clarified)
    stuck = context.blocked | frozenset(context.to_clarify)
    ids: list[str] = []
    for scene_id, item in context.entities.items():
        if (focus_id is not None and scene_id != focus_id) or scene_id in stuck:
            continue
        if item.resolution.resolved and item.resolution.best.entity_id not in ids:
            ids.append(item.resolution.best.entity_id)
    return ids[:TRIED_ENTITIES]


async def first_stored(store: SoundStore, entity_ids: list[str]) -> str | None:
    """Return the path of the first of these entities whose sound was uploaded."""
    for entity_id in entity_ids:
        try:
            await store.get(entity_id)
        except (InvalidKeyError, ObjectNotFoundError):
            continue
        except StorageUnavailableError:
            return None
        return sound_path(entity_id)
    return None
