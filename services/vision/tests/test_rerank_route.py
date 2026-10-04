from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_main import FakeDetector
from vision import main
from vision.config import MAX_PASSAGES, Settings
from vision.errors import RerankerUnavailableError
from vision.reranker import RerankerStatus, RerankResult


class FakeReranker:
    """A reranker that scores a passage by its length and records its calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.warmups = 0
        self.error: Exception | None = None

    def warmup(self) -> None:
        self.warmups += 1
        if self.error is not None:
            raise self.error

    def status(self) -> RerankerStatus:
        return RerankerStatus(model="fake/reranker", loaded=True, error=None)

    def rerank(self, query: str, passages: Sequence[str]) -> RerankResult:
        if self.error is not None:
            raise self.error
        self.calls.append((query, list(passages)))
        return RerankResult(
            scores=[len(text) / 100 for text in passages], model="fake/reranker", ms=7
        )


@pytest.fixture
def ranker() -> FakeReranker:
    return FakeReranker()


@pytest.fixture
def client(settings: Settings, ranker: FakeReranker) -> Iterator[TestClient]:
    app = main.create_app(settings, FakeDetector(), ranker)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_rerank_scores_every_passage_in_order(client: TestClient, ranker: FakeReranker) -> None:
    response = client.post("/rerank", json={"query": "إحياء الأرض", "passages": ["ab", "abcd"]})

    assert response.status_code == 200
    assert response.json() == {"scores": [0.02, 0.04], "model": "fake/reranker", "ms": 7}
    assert ranker.calls == [("إحياء الأرض", ["ab", "abcd"])]


@pytest.mark.parametrize(
    "body",
    [
        {"query": "", "passages": ["a"]},
        {"query": "q", "passages": []},
        {"query": "q", "passages": [""]},
        {"query": "q", "passages": ["a"] * (MAX_PASSAGES + 1)},
        {"passages": ["a"]},
    ],
)
def test_rerank_validates_its_body(client: TestClient, body: dict[str, object]) -> None:
    response = client.post("/rerank", json=body)

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_rerank_without_its_model_answers_503(client: TestClient, ranker: FakeReranker) -> None:
    ranker.error = RerankerUnavailableError("the weights are missing")

    response = client.post("/rerank", json={"query": "q", "passages": ["p"]})

    assert response.status_code == 503
    assert response.json() == {"error": "reranker_unavailable", "detail": "the weights are missing"}


def test_health_reports_the_reranker_apart_from_the_detector(client: TestClient) -> None:
    body = client.get("/health").json()

    assert (body["ok"], body["reranker"], body["rerankerLoaded"]) == (True, "fake/reranker", True)
    assert body["rerankerError"] is None


def test_the_reranker_warms_up_at_startup_when_asked(
    weights_dir: Path, ranker: FakeReranker, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(
        _env_file=None,
        vision_weights_dir=weights_dir,
        vision_warmup=False,
        vision_reranker_warmup=True,
    )
    with TestClient(main.create_app(settings, FakeDetector(), ranker)) as client:
        assert client.get("/health").status_code == 200
    assert ranker.warmups == 1

    ranker.error = RerankerUnavailableError("weights are missing")
    with (
        caplog.at_level(logging.WARNING, logger="vision"),
        TestClient(main.create_app(settings, FakeDetector(), ranker)) as client,
    ):
        assert client.get("/health").status_code == 200
    assert "reranker warm-up skipped: weights are missing" in caplog.text


def test_the_reranker_model_must_be_a_hub_id(weights_dir: Path) -> None:
    with pytest.raises(ValueError, match="vision_reranker_model"):
        Settings(
            _env_file=None, vision_weights_dir=weights_dir, vision_reranker_model="not a hub id"
        )
