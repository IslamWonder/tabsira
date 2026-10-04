"""
The cross-encoder reranker: reads a query and a passage together and scores how well they match.

The API sends the 20 to 30 candidates its hybrid search found and orders them
by these scores (master prompt v2 §9). The model is chosen by the API's
retrieval benchmark (docs/BENCHMARK.md) among the Hugging Face sequence
classifiers this module can run: one logit (bge-reranker, read through a
sigmoid) or two (the msmarco passage rerankers, read as the probability of the
"relevant" class). The weights are fetched ahead of time by
`scripts/fetch-weights.sh` into the weights directory; the service runs
Transformers offline and never downloads anything.

Heavy imports (torch, Transformers) happen when the model is first needed.
"""

from __future__ import annotations

import importlib
import logging
import math
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from vision.config import Settings
from vision.errors import RerankerUnavailableError

logger = logging.getLogger(__name__)

# Pairs scored per forward pass: enough to fill the CPU, few enough to bound memory.
BATCH_SIZE = 16

# Loads (tokenizer, model) from a local directory.
RerankerLoader = Callable[[Path], tuple[Any, Any]]


def model_directory(weights_dir: Path, model: str) -> Path:
    """Return where the weights of a Hugging Face model id live: weights/rerankers/<org>--<name>."""
    return weights_dir / "rerankers" / model.replace("/", "--")


def configure_offline() -> None:
    """Keep Transformers and the Hugging Face hub from reaching the network at run time."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def load_transformers_model(directory: Path) -> tuple[Any, Any]:
    """Load a sequence-classification model and its tokenizer from `directory`, for inference."""
    configure_offline()
    transformers = importlib.import_module("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(str(directory))
    model = transformers.AutoModelForSequenceClassification.from_pretrained(str(directory))
    model.eval()
    return tokenizer, model


def relevance(logits: Sequence[float]) -> float:
    """Turn one pair's logits into a score from 0 to 1."""
    if len(logits) == 1:
        return 1.0 / (1.0 + math.exp(-logits[0]))
    top = max(logits)
    exps = [math.exp(value - top) for value in logits]
    return exps[1] / sum(exps)


@dataclass(frozen=True)
class RerankResult:
    scores: list[float]
    model: str
    ms: int


@dataclass(frozen=True)
class RerankerStatus:
    model: str
    loaded: bool
    error: str | None


class Reranker(Protocol):
    """What the service needs from a reranker."""

    def warmup(self) -> None:
        """Load the model now instead of on the first request."""
        ...

    def status(self) -> RerankerStatus:
        """Describe the reranker without loading it."""
        ...

    def rerank(self, query: str, passages: Sequence[str]) -> RerankResult:
        """Score every passage against the query; raise RerankerUnavailableError when it cannot."""
        ...


class TransformersReranker:
    """A Hugging Face cross-encoder run on the CPU with torch, one request at a time."""

    def __init__(
        self, settings: Settings, loader: RerankerLoader = load_transformers_model
    ) -> None:
        self._model_id = settings.vision_reranker_model
        self._directory = model_directory(
            settings.vision_weights_dir, settings.vision_reranker_model
        )
        self._max_length = settings.vision_reranker_max_length
        self._loader = loader
        self._lock = threading.Lock()
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._load_error: str | None = None

    def warmup(self) -> None:
        self.rerank("warm-up", ["warm-up"])

    def status(self) -> RerankerStatus:
        if self._model is not None:
            error = None
        elif self._directory.is_dir():
            error = self._load_error
        else:
            error = self._missing_message()
        return RerankerStatus(model=self._model_id, loaded=self._model is not None, error=error)

    def _missing_message(self) -> str:
        return f"the weights of {self._model_id} are missing; run scripts/fetch-weights.sh"

    def _load(self) -> tuple[Any, Any]:
        """Return the tokenizer and the model, loading them the first time. Called with the lock held."""
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model
        if not self._directory.is_dir():
            raise RerankerUnavailableError(self._missing_message())
        started = time.perf_counter()
        try:
            tokenizer, model = self._loader(self._directory)
        except Exception as exc:  # a damaged or partial download fails in many ways
            self._load_error = f"{self._model_id} could not be loaded ({type(exc).__name__})"
            logger.exception("loading %s failed", self._directory)
            raise RerankerUnavailableError(self._load_error) from exc
        self._load_error = None
        self._tokenizer, self._model = tokenizer, model
        logger.info("loaded %s in %d ms", self._model_id, (time.perf_counter() - started) * 1000)
        return tokenizer, model

    def rerank(self, query: str, passages: Sequence[str]) -> RerankResult:
        with self._lock:
            started = time.perf_counter()
            tokenizer, model = self._load()
            torch = importlib.import_module("torch")
            scores: list[float] = []
            with torch.inference_mode():
                for start in range(0, len(passages), BATCH_SIZE):
                    chunk = list(passages[start : start + BATCH_SIZE])
                    encoded = tokenizer(
                        [query] * len(chunk),
                        chunk,
                        padding=True,
                        truncation="only_second",
                        max_length=self._max_length,
                        return_tensors="pt",
                    )
                    logits = model(**encoded).logits.tolist()
                    scores += [round(relevance(row), 6) for row in logits]
            ms = round((time.perf_counter() - started) * 1000)
        logger.info("%s scored %d passages in %d ms", self._model_id, len(passages), ms)
        return RerankResult(scores=scores, model=self._model_id, ms=ms)
