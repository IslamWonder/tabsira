"""A tiny gold set on disk, a mock detector and fake clients for the benchmark tests."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallLog
from src.config import AiProvider, BoxCoordinates, OpenAISettings, OvhSettings
from src.evaluation.benchmark import Cell
from tests.fakes import FakeModelClient

# Two scenes told apart by their width: the prompt states it.
PHONE_WIDTH, WINE_WIDTH = 64, 96
DETECTION = {
    "id": "d1",
    "label": "smartphone",
    "labelArabic": "هاتف ذكي",
    "confidence": 0.8,
    "bbox": {"x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5},
}


def _jpeg(width: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, 64), (120, 80, 40)).save(buffer, "JPEG")
    return buffer.getvalue()


def _scene(identifier: str, data: bytes, *, sensitive: bool) -> dict[str, Any]:
    return {
        "id": identifier,
        "image": f"{identifier}.jpg",
        "sha256": hashlib.sha256(data).hexdigest(),
        "provenance": {
            "origin": "generated",
            "source": "test",
            "generator": "test",
            "prompt": None,
        },
        "kind": "sensitive" if sensitive else "clear",
        "notes": "",
        "required_entities": [["هاتف", "phone"]] if not sensitive else [["نبيذ", "wine"]],
        "expected_actions": [["ينظر"]] if not sensitive else [],
        "forbidden_actions": [["يقرا"]],
        "inferred_only_actions": [],
        "forbidden_entities": [["شخص"]],
        "sensitive": sensitive,
        "expects_clarification": True if not sensitive else None,
    }


def write_gold(directory: Path) -> Path:
    """Write two scenes (an ordinary phone, a sensitive wine) and their gold file."""
    phone, wine = _jpeg(PHONE_WIDTH), _jpeg(WINE_WIDTH)
    (directory / "phone.jpg").write_bytes(phone)
    (directory / "wine.jpg").write_bytes(wine)
    gold = {
        "version": 1,
        "description": "test",
        "provenance_note": "Generated for the test.",
        "rules": {
            "forbidden_actions": [{"claim": "praying", "patterns": ["يصلي"]}],
            "identity_terms": ["طفل"],
        },
        "scenes": [
            _scene("phone", phone, sensitive=False),
            _scene("wine", wine, sensitive=True),
        ],
    }
    path = directory / "gold.json"
    path.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    return path


def detector_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "detections": [DETECTION],
            "width": 64,
            "height": 64,
            "model": "yoloe-test",
            "ms": 12,
            "vocabularyMode": "open",
        },
    )


def width_of(call: dict[str, Any]) -> int:
    found = re.search(r"The photo is (\d+) pixels wide", call["user"])
    assert found is not None
    return int(found.group(1))


def answer(
    *,
    box: list[float] | None = None,
    detector_id: str | None = "d1",
    misses_sensitive: bool = False,
    description: str | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A model that names the scene's main thing; its box is given in the asked system."""

    def respond(call: dict[str, Any]) -> dict[str, Any]:
        wine = width_of(call) == WINE_WIDTH
        hidden = "not available" in call["user"]
        return {
            "description": description or ("زجاجة نبيذ" if wine else "هاتف على مكتب"),
            "entities": [
                {
                    "id": "e1",
                    "label": "wine" if wine else "phone",
                    "label_arabic": "نبيذ" if wine else "هاتف",
                    "detector_id": None if hidden else detector_id,
                    "box": box,
                    "status": "observed",
                }
            ],
            "actions": [],
            "relations": [
                {"subject_id": "e1", "predicate": "ينظر إلى", "object_id": "e1", "evidence": "ظاهر"}
            ],
            "ambiguities": [],
            "clarification_question": None if wine else "ماذا تفعل به؟",
            "sensitive": ["alcohol"] if wine and not misses_sensitive else [],
        }

    return respond


def broken(_: dict[str, Any]) -> AiCallError:
    return AiCallError(AiErrorCode.TIMEOUT, "slow")


def cell(
    name: str,
    provider: AiProvider = AiProvider.OVH,
    *,
    model: str = "Qwen3.8-27B",
    coordinates: BoxCoordinates = BoxCoordinates.THOUSANDTHS,
    guard: str = "",
) -> Cell:
    return Cell(
        name=name,
        provider=provider,
        model=model,
        reasoning_effort="none",
        box_coordinates=coordinates,
        guard_model=guard,
    )


Behaviour = tuple[Callable[[dict[str, Any]], Any], int]


def factory(behaviours: dict[str, Behaviour]) -> Callable[[Cell, CallLog], FakeModelClient]:
    """Fake clients: each cell answers with its behaviour and its latency."""

    def build(chosen: Cell, log: CallLog) -> FakeModelClient:
        respond, latency = behaviours[chosen.name]
        settings = (
            OvhSettings(vision_model=chosen.model, box_coordinates=chosen.box_coordinates)
            if chosen.provider == AiProvider.OVH
            else OpenAISettings(
                vision_model=chosen.model,
                box_coordinates=chosen.box_coordinates,
                guard_model=chosen.guard_model,
            )
        )
        return FakeModelClient(
            chosen.provider,
            settings,
            answers=[respond],
            moderations=[(False, [])],
            log=log,
            latency_ms=latency,
        )

    return build
