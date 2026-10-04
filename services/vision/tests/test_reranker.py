from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from vision import reranker
from vision.config import Settings
from vision.errors import RerankerUnavailableError
from vision.reranker import (
    BATCH_SIZE,
    TransformersReranker,
    configure_offline,
    load_transformers_model,
    model_directory,
    relevance,
)


class FakeTokenizer:
    """Records the pairs it was asked to encode; the encoding is the passage list itself."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, queries: list[str], passages: list[str], **options: Any) -> dict[str, Any]:
        self.calls.append({"queries": queries, "passages": passages, **options})
        return {"passages": passages}


class FakeLogits:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


class FakeCrossEncoder:
    """One logit per pair: the passage length, so longer passages score higher."""

    def __call__(self, passages: list[str]) -> SimpleNamespace:
        return SimpleNamespace(logits=FakeLogits([[float(len(text)) - 3] for text in passages]))


def make_reranker(settings: Settings, loader: Any) -> TransformersReranker:
    model_directory(settings.vision_weights_dir, settings.vision_reranker_model).mkdir(parents=True)
    return TransformersReranker(settings, loader)


def test_the_weights_of_a_model_live_under_its_id() -> None:
    assert model_directory(Path("/w"), "BAAI/bge-reranker-v2-m3") == Path(
        "/w/rerankers/BAAI--bge-reranker-v2-m3"
    )


def test_one_logit_is_read_through_a_sigmoid_and_two_as_the_relevant_class() -> None:
    assert relevance([0.0]) == pytest.approx(0.5)
    assert relevance([10.0]) > 0.99
    assert relevance([0.0, 0.0]) == pytest.approx(0.5)
    assert relevance([-5.0, 5.0]) > 0.99


def test_transformers_is_kept_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(name, "0")

    configure_offline()

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_the_model_and_tokenizer_load_from_the_local_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    loaded: list[tuple[str, str]] = []
    model = SimpleNamespace(eval=lambda: loaded.append(("eval", "")))

    class Auto:
        def __init__(self, kind: str, value: Any) -> None:
            self.kind, self.value = kind, value

        def from_pretrained(self, path: str) -> Any:
            loaded.append((self.kind, path))
            return self.value

    fake = ModuleType("transformers")
    fake.AutoTokenizer = Auto("tokenizer", "tok")  # type: ignore[attr-defined]
    fake.AutoModelForSequenceClassification = Auto("model", model)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", fake)
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(name, "0")

    assert load_transformers_model(tmp_path) == ("tok", model)
    assert loaded == [("tokenizer", str(tmp_path)), ("model", str(tmp_path)), ("eval", "")]


def test_status_names_missing_weights_without_loading(settings: Settings) -> None:
    status = TransformersReranker(settings, lambda _path: pytest.fail("loaded")).status()

    assert status.model == "BAAI/bge-reranker-v2-m3"
    assert not status.loaded
    assert "missing; run scripts/fetch-weights.sh" in (status.error or "")


def test_rerank_without_weights_is_unavailable(settings: Settings) -> None:
    with pytest.raises(RerankerUnavailableError, match="missing"):
        TransformersReranker(settings).rerank("q", ["p"])


def test_scores_come_in_passage_order_in_batches_and_the_model_loads_once(
    settings: Settings,
) -> None:
    tokenizer = FakeTokenizer()
    loads: list[Path] = []

    def loader(path: Path) -> tuple[Any, Any]:
        loads.append(path)
        return tokenizer, FakeCrossEncoder()

    ranker = make_reranker(settings, loader)
    passages = ["abc", "abcdefgh"] * (BATCH_SIZE // 2 + 1)

    first = ranker.rerank("سؤال", passages)
    ranker.warmup()

    assert len(first.scores) == len(passages)
    assert first.scores[0] == pytest.approx(0.5)
    assert first.scores[1] > 0.99
    assert first.model == "BAAI/bge-reranker-v2-m3"
    assert len(loads) == 1
    assert [len(call["passages"]) for call in tokenizer.calls[:2]] == [BATCH_SIZE, 2]
    assert tokenizer.calls[0]["queries"] == ["سؤال"] * BATCH_SIZE
    assert tokenizer.calls[0]["truncation"] == "only_second"
    assert tokenizer.calls[0]["max_length"] == settings.vision_reranker_max_length
    assert ranker.status().loaded


def test_a_model_that_fails_to_load_is_reported_and_retried(settings: Settings) -> None:
    attempts: list[int] = []

    def loader(_path: Path) -> tuple[Any, Any]:
        attempts.append(1)
        if len(attempts) == 1:
            message = "damaged"
            raise OSError(message)
        return FakeTokenizer(), FakeCrossEncoder()

    ranker = make_reranker(settings, loader)

    with pytest.raises(RerankerUnavailableError, match=r"could not be loaded \(OSError\)"):
        ranker.rerank("q", ["p"])
    assert "OSError" in (ranker.status().error or "")

    assert len(ranker.rerank("q", ["p"]).scores) == 1
    assert ranker.status().error is None


def test_the_module_reads_torch_lazily() -> None:
    assert "torch" not in reranker.__dict__
