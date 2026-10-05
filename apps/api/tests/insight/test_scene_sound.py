"""The sound of a scene: which ontology entities it may come from, and the first one stored."""

from __future__ import annotations

from src.pipeline.insight.context import build_context
from src.scans.sound import TRIED_ENTITIES, candidate_entities, first_stored, sound_path
from src.storage.base import InvalidKeyError, ObjectNotFoundError, StorageUnavailableError
from src.storage.sounds import SoundStore
from tests.insight.support import entity, rain_scene, scene


class FakeStore(SoundStore):
    """Answers or fails per entity id, and records what it was asked."""

    def __init__(self, answers: dict[str, Exception | None]) -> None:
        super().__init__(bucket="", client=None, root=None)  # type: ignore[arg-type]
        self.answers = answers
        self.asked: list[str] = []

    async def get(self, entity_id: str) -> bytes:
        self.asked.append(entity_id)
        error = self.answers.get(entity_id, ObjectNotFoundError("none"))
        if error is not None:
            raise error
        return b"ID3"


async def best_ids(store, a_scene) -> dict[str, str]:
    context = await build_context(store, a_scene, clarified=False)
    return {
        scene_id: item.resolution.best.entity_id
        for scene_id, item in context.entities.items()
        if item.resolution.resolved
    }


async def test_the_resolved_entities_come_in_the_scenes_order(store):
    expected = await best_ids(store, rain_scene())

    ids = await candidate_entities(store, rain_scene(), focus_id=None, clarified=False)

    assert ids == [expected["e1"], expected["e2"]]


async def test_a_blocked_or_unclear_entity_never_gives_the_sound(store):
    with_hand = scene(
        [
            entity("e1", "hand", "يد"),
            entity("e2", "zzqq", "شيء غامض جدا"),
            entity("e3", "rain", "مطر"),
        ]
    )
    expected = await best_ids(store, with_hand)

    ids = await candidate_entities(store, with_hand, focus_id=None, clarified=False)

    assert ids == [expected["e3"]]


async def test_a_focus_keeps_only_its_entity(store):
    expected = await best_ids(store, rain_scene())

    ids = await candidate_entities(store, rain_scene(), focus_id="e2", clarified=False)

    assert ids == [expected["e2"]]


async def test_a_sensitive_scene_has_no_sound(store):
    assert (
        await candidate_entities(store, rain_scene(sensitive=True), focus_id=None, clarified=False)
        == []
    )


async def test_the_same_entity_is_tried_once(store):
    twice = scene([entity("e1", "rain", "مطر"), entity("e2", "rain", "مطر")])

    assert len(await candidate_entities(store, twice, focus_id=None, clarified=False)) == 1


async def test_only_the_first_few_entities_are_tried(store):
    many = scene(
        [
            entity("e1", "rain", "مطر"),
            entity("e2", "soil", "تربة"),
            entity("e3", "tree", "شجرة"),
            entity("e4", "sun", "شمس"),
            entity("e5", "sea", "بحر"),
        ]
    )
    expected = list(dict.fromkeys((await best_ids(store, many)).values()))

    ids = await candidate_entities(store, many, focus_id=None, clarified=False)

    assert len(expected) > TRIED_ENTITIES
    assert ids == expected[:TRIED_ENTITIES]


async def test_the_first_uploaded_sound_is_chosen():
    store = FakeStore({"E002": None, "E003": None})

    assert await first_stored(store, ["E001", "E002", "E003"]) == sound_path("E002")
    assert store.asked == ["E001", "E002"]


async def test_an_id_the_store_refuses_is_skipped():
    store = FakeStore({"bad": InvalidKeyError("no"), "E004": None})

    assert await first_stored(store, ["bad", "E004"]) == "/sounds/ontology/E004"


async def test_a_storage_that_does_not_answer_gives_no_sound():
    store = FakeStore({"E001": StorageUnavailableError("down"), "E002": None})

    assert await first_stored(store, ["E001", "E002"]) is None
    assert store.asked == ["E001"]


async def test_no_candidate_means_no_sound():
    assert await first_stored(FakeStore({}), []) is None
