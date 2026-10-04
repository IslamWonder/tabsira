"""Builders for evaluation tests: gold scenes, scenes and model answers."""

from __future__ import annotations

from typing import Any

from src.config import AiProvider
from src.evaluation.gold import ForbiddenClaim, GoldRules, GoldScene, Provenance
from src.pipeline.schemas import (
    BBox,
    EntityOrigin,
    EvidenceStatus,
    SceneAction,
    SceneAnalysis,
    SceneEntity,
    SceneRelation,
)

RULES = GoldRules(
    forbidden_actions=[ForbiddenClaim(claim="praying", patterns=["يصلي", "pray"])],
    identity_terms=["طفل", "طفله", "رجال", "girl"],
)


def gold_scene(**values: Any) -> GoldScene:
    base: dict[str, Any] = {
        "id": "scene",
        "image": "scene.jpg",
        "sha256": "0" * 64,
        "provenance": Provenance(origin="generated", source="s", generator="g", prompt=None),
        "kind": "clear",
        "notes": "",
        "required_entities": [["هاتف", "phone"], ["دفتر", "notebook"]],
        "expected_actions": [["ينظر", "look"]],
        "forbidden_actions": [["يقرا", "read"]],
        "inferred_only_actions": [["يطعم", "feed"]],
        "forbidden_entities": [["شخص", "person"]],
        "sensitive": False,
        "expects_clarification": True,
    }
    return GoldScene(**{**base, **values})


def entity(identifier: str, label: str, arabic: str, **values: Any) -> SceneEntity:
    base: dict[str, Any] = {
        "id": identifier,
        "label": label,
        "label_arabic": arabic,
        "bbox": None,
        "origin": EntityOrigin.VLM,
        "status": EvidenceStatus.OBSERVED,
    }
    return SceneEntity(**{**base, **values})


def action(label: str, status: EvidenceStatus = EvidenceStatus.OBSERVED) -> SceneAction:
    return SceneAction(
        id=f"a-{label}",
        label=label,
        actor_ids=[],
        target_ids=[],
        visible_evidence=["قرينة"],
        status=status,
    )


def analysis(**values: Any) -> SceneAnalysis:
    base: dict[str, Any] = {
        "description": "هاتف على دفتر",
        "entities": [],
        "actions": [],
        "relations": [],
        "ambiguities": [],
        "clarification_question": None,
        "sensitive": [],
        "detector_available": True,
        "unconfirmed_detection_ids": [],
        "rejected": [],
        "provider": AiProvider.OVH,
        "model": "m",
        "prompt_version": "v",
    }
    return SceneAnalysis(**{**base, **values})


def relation(predicate: str) -> SceneRelation:
    return SceneRelation(subject_id="e1", predicate=predicate, object_id="e2", evidence="ظاهر")


HALF = BBox(x=0.0, y=0.0, width=0.5, height=0.5)
QUARTER = BBox(x=0.0, y=0.0, width=0.25, height=0.5)
