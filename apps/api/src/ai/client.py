"""
The provider adapter: one client for OVHcloud AI Endpoints and OpenAI.

Both speak the OpenAI HTTP API, so one adapter serves both and switching is the
single `AI_PROVIDER` setting. It talks to the API with httpx directly rather
than through the `openai` SDK: the SDK (3.x) brings a second HTTP stack and its
own hidden retries, while TABSIRA needs to count every attempt in the call
record, retry an answer that does not match its schema, read OVH's non-standard
fields, and mock the provider at one transport in tests. Three endpoints are
used: chat completions with strict JSON-schema output, embeddings and (OpenAI
only) moderations.

Every call is bounded: a timeout per attempt, a fixed number of retries with
exponential backoff, and a `CallRecord` written whatever the outcome.
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallKind, CallLog, CallRecord, Usage, cost_usd
from src.ai.strict_schema import response_format
from src.config import AiProvider, AiStage, ProviderSettings, Settings, refuse_forbidden_model

# A provider that asks us to wait longer than this is treated as down for now.
MAX_BACKOFF_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 10.0
# Longest provider error message kept in an exception (logs only).
ERROR_DETAIL_CHARS = 200

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

_STATUS_CODES: dict[int, AiErrorCode] = {
    400: AiErrorCode.BAD_REQUEST,
    401: AiErrorCode.UNAUTHORIZED,
    403: AiErrorCode.UNAUTHORIZED,
    404: AiErrorCode.NOT_FOUND,
    408: AiErrorCode.TIMEOUT,
    422: AiErrorCode.BAD_REQUEST,
    429: AiErrorCode.RATE_LIMITED,
}


@dataclass(frozen=True)
class ModelImage:
    """An image as sent to a model: bytes already stripped of metadata."""

    data: bytes
    mime: str = "image/jpeg"

    def data_url(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode('ascii')}"


@dataclass(frozen=True)
class ChatResult[T: BaseModel]:
    """A validated structured answer and the record of the call that produced it."""

    value: T
    record: CallRecord


@dataclass(frozen=True)
class EmbeddingResult:
    """One vector per input text, in input order."""

    vectors: list[list[float]]
    record: CallRecord


@dataclass(frozen=True)
class ModerationResult:
    """The provider's moderation verdict on an image or on a text."""

    flagged: bool
    # Categories the provider flagged, with its own names (sexual, violence/graphic, ...).
    categories: list[str]
    scores: dict[str, float]
    record: CallRecord


type Parser[R] = Callable[[Mapping[str, Any]], R]


class ModelClient(ABC):
    """What a pipeline stage may ask of a provider; stages depend on this, tests fake it."""

    @property
    @abstractmethod
    def provider(self) -> AiProvider:
        """The provider that serves the calls."""

    @property
    @abstractmethod
    def settings(self) -> ProviderSettings:
        """The provider's settings block."""

    @abstractmethod
    async def chat_json[T: BaseModel](
        self,
        schema: type[T],
        *,
        stage: AiStage,
        system: str,
        user: str,
        images: Sequence[ModelImage] = (),
        model: str | None = None,
        max_output_tokens: int = 4096,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult[T]:
        """Ask for an answer that matches `schema`."""

    @abstractmethod
    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> EmbeddingResult:
        """Embed one batch of texts."""

    @abstractmethod
    async def moderate_image(
        self, image: ModelImage, *, model: str | None = None
    ) -> ModerationResult:
        """Run the provider's image moderation."""

    async def moderate_text(self, text: str, *, model: str | None = None) -> ModerationResult:
        """
        Run the provider's text moderation.

        Not abstract: a client that cannot moderate text says so, and the callers
        that need a verdict treat that as "ask a person".
        """
        message = f"{self.provider.value} has no text moderation"
        raise AiCallError(AiErrorCode.NOT_SUPPORTED, message)


class ProviderClient(ModelClient):
    """Calls one provider's models for the pipeline stages."""

    def __init__(
        self,
        provider: AiProvider,
        settings: ProviderSettings,
        http: httpx.AsyncClient,
        *,
        timeout_seconds: float,
        max_retries: int,
        backoff_seconds: float,
        log: CallLog | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._http = http
        self._timeout = httpx.Timeout(timeout_seconds, connect=CONNECT_TIMEOUT_SECONDS)
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._log = log
        self._sleep = sleep
        self._clock = clock

    @property
    def provider(self) -> AiProvider:
        return self._provider

    @property
    def settings(self) -> ProviderSettings:
        return self._settings

    async def chat_json[T: BaseModel](
        self,
        schema: type[T],
        *,
        stage: AiStage,
        system: str,
        user: str,
        images: Sequence[ModelImage] = (),
        model: str | None = None,
        max_output_tokens: int = 4096,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult[T]:
        """Ask for an answer that matches `schema`; return it validated, or raise AiCallError."""
        chosen = self._model(stage, model)
        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        content += [
            {"type": "image_url", "image_url": {"url": image.data_url()}} for image in images
        ]
        body: dict[str, Any] = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "response_format": response_format(schema),
            "max_completion_tokens": max_output_tokens,
        }
        effort = self._settings.reasoning_effort if reasoning_effort is None else reasoning_effort
        if effort:
            body["reasoning_effort"] = effort
        if temperature is not None:
            body["temperature"] = temperature

        def parse(payload: Mapping[str, Any]) -> T:
            return _parse_chat(payload, schema)

        value, record = await self._call(
            CallKind.CHAT, stage, chosen, "/chat/completions", body, parse
        )
        return ChatResult(value=value, record=record)

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> EmbeddingResult:
        """Embed one batch of texts with the embedding model."""
        chosen = self._model(AiStage.EMBEDDING, model)
        body: dict[str, Any] = {"model": chosen, "input": list(texts)}
        if dimensions is not None:
            body["dimensions"] = dimensions

        def parse(payload: Mapping[str, Any]) -> list[list[float]]:
            return _parse_embeddings(payload, len(texts))

        vectors, record = await self._call(
            CallKind.EMBEDDING, AiStage.EMBEDDING, chosen, "/embeddings", body, parse
        )
        return EmbeddingResult(vectors=vectors, record=record)

    async def moderate_image(
        self, image: ModelImage, *, model: str | None = None
    ) -> ModerationResult:
        """Run the provider's image moderation (OpenAI only)."""
        return await self._moderate(
            [{"type": "image_url", "image_url": {"url": image.data_url()}}], model
        )

    async def moderate_text(self, text: str, *, model: str | None = None) -> ModerationResult:
        """Run the provider's text moderation (OpenAI only)."""
        return await self._moderate(text, model)

    async def _moderate(self, content: Any, model: str | None) -> ModerationResult:
        """Send one input to the moderations endpoint and read the verdict."""
        if self._provider != AiProvider.OPENAI:
            raise AiCallError(
                AiErrorCode.NOT_SUPPORTED, f"{self._provider.value} has no moderation endpoint"
            )
        chosen = self._model(AiStage.GUARD, model)
        body = {"model": chosen, "input": content}
        parsed, record = await self._call(
            CallKind.MODERATION, AiStage.GUARD, chosen, "/moderations", body, _parse_moderation
        )
        flagged, categories, scores = parsed
        return ModerationResult(
            flagged=flagged, categories=categories, scores=scores, record=record
        )

    def _model(self, stage: AiStage, model: str | None) -> str:
        chosen = model or self._settings.model_for(stage)
        if not chosen:
            message = f"no {stage.value} model is set for {self._provider.value}"
            raise AiCallError(AiErrorCode.NOT_CONFIGURED, message)
        try:
            refuse_forbidden_model(chosen)
        except ValueError as error:
            raise AiCallError(AiErrorCode.FORBIDDEN_MODEL, str(error)) from None
        if not self._settings.api_key.get_secret_value():
            message = f"the {self._provider.value} API key is empty"
            raise AiCallError(AiErrorCode.NOT_CONFIGURED, message)
        return chosen

    async def _call[R](
        self,
        kind: CallKind,
        stage: AiStage,
        model: str,
        path: str,
        body: Mapping[str, Any],
        parse: Parser[R],
    ) -> tuple[R, CallRecord]:
        started_at = datetime.now(UTC)
        started = self._clock()
        usage = Usage()
        attempts = 0
        finish_reason: str | None = None
        retried: list[AiErrorCode] = []

        def record(*, ok: bool, error_code: AiErrorCode | None = None) -> CallRecord:
            made = CallRecord(
                provider=self._provider,
                model=model,
                stage=stage,
                kind=kind,
                started_at=started_at,
                latency_ms=round((self._clock() - started) * 1000),
                attempts=attempts,
                usage=usage,
                cost_usd=cost_usd(self._settings.prices.get(model), usage),
                ok=ok,
                error_code=error_code,
                finish_reason=finish_reason,
                retried_errors=tuple(retried),
            )
            if self._log is not None:
                self._log.add(made)
            return made

        while True:
            attempts += 1
            try:
                payload = await self._post(path, body)
                usage = usage + Usage.from_response(payload.get("usage"))
                finish_reason = _finish_reason(payload)
                value = parse(payload)
            except AiCallError as error:
                if error.retryable and attempts <= self._max_retries:
                    retried.append(error.code)
                    await self._sleep(self._delay(attempts, error.retry_after))
                    continue
                failed = record(ok=False, error_code=error.code)
                raise AiCallError(error.code, _reason(error), record=failed) from None
            return value, record(ok=True)

    async def _post(self, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        url = self._settings.base_url.rstrip("/") + path
        headers = {"Authorization": f"Bearer {self._settings.api_key.get_secret_value()}"}
        try:
            response = await self._http.post(url, json=body, headers=headers, timeout=self._timeout)
        except httpx.ConnectTimeout:
            # No connection was made: the network, not the provider's speed.
            raise AiCallError(AiErrorCode.NETWORK, "cannot reach the provider") from None
        except httpx.TimeoutException:
            raise AiCallError(AiErrorCode.TIMEOUT, "the provider did not answer in time") from None
        except httpx.TransportError as error:
            message = f"cannot reach the provider ({type(error).__name__})"
            raise AiCallError(AiErrorCode.NETWORK, message) from None
        if response.status_code != httpx.codes.OK:
            raise _status_error(response)
        try:
            payload = response.json()
        except ValueError:
            raise AiCallError(AiErrorCode.SERVER_ERROR, "the answer is not JSON") from None
        if not isinstance(payload, Mapping):
            raise AiCallError(AiErrorCode.SERVER_ERROR, "the answer is not a JSON object")
        return payload

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        delay = self._backoff * 2.0 ** (attempt - 1)
        if retry_after is not None:
            delay = max(delay, retry_after)
        return min(delay, MAX_BACKOFF_SECONDS)


def client_for(
    settings: Settings,
    http: httpx.AsyncClient,
    *,
    provider: AiProvider | None = None,
    log: CallLog | None = None,
) -> ProviderClient:
    """Build the client of `provider`, or of the active provider, from the settings."""
    chosen = provider or settings.ai_provider
    block = settings.ai_ovh if chosen == AiProvider.OVH else settings.ai_openai
    return ProviderClient(
        chosen,
        block,
        http,
        timeout_seconds=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
        backoff_seconds=settings.ai_retry_backoff_seconds,
        log=log,
    )


def _reason(error: AiCallError) -> str:
    return str(error).removeprefix(f"{error.code.value}: ")


def _status_error(response: httpx.Response) -> AiCallError:
    status = response.status_code
    code = _STATUS_CODES.get(status)
    if code is None:
        code = AiErrorCode.SERVER_ERROR if status >= 500 else AiErrorCode.BAD_REQUEST
    retry_after: float | None = None
    if code == AiErrorCode.RATE_LIMITED:
        try:
            retry_after = float(response.headers.get("retry-after", ""))
        except ValueError:
            retry_after = None
    return AiCallError(
        code, f"HTTP {status}: {_provider_message(response)}", retry_after=retry_after
    )


def _provider_message(response: httpx.Response) -> str:
    """Return the provider's own error message, shortened; never the request."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:ERROR_DETAIL_CHARS]
    error = payload.get("error") if isinstance(payload, Mapping) else None
    message = error.get("message") if isinstance(error, Mapping) else error
    return str(message or payload)[:ERROR_DETAIL_CHARS]


def _finish_reason(payload: Mapping[str, Any]) -> str | None:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        reason = choices[0].get("finish_reason")
        return reason if isinstance(reason, str) else None
    return None


def _parse_chat[T: BaseModel](payload: Mapping[str, Any], schema: type[T]) -> T:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "the answer has no choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "the answer has no message")
    if message.get("refusal"):
        raise AiCallError(AiErrorCode.REFUSED, "the model refused to answer")
    if _finish_reason(payload) == "length":
        raise AiCallError(AiErrorCode.TRUNCATED, "the answer hit the output token limit")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "the answer is empty")
    try:
        value = schema.model_validate_json(_json_text(content))
    except ValidationError as error:
        message_text = f"the answer does not match {schema.__name__} ({error.error_count()} errors)"
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, message_text) from None
    return value


def _json_text(content: str) -> str:
    """Remove what some models wrap around JSON even in structured mode."""
    text = _THINK_BLOCK.sub("", content).strip()
    fenced = _CODE_FENCE.match(text)
    return fenced.group(1) if fenced else text


def _parse_embeddings(payload: Mapping[str, Any], expected: int) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected:
        raise AiCallError(
            AiErrorCode.INVALID_OUTPUT, "the answer does not hold one vector per text"
        )
    try:
        ordered = sorted(data, key=lambda item: int(item["index"]))
        return [[float(number) for number in item["embedding"]] for item in ordered]
    except (KeyError, TypeError, ValueError):
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "a vector is malformed") from None


def _parse_moderation(payload: Mapping[str, Any]) -> tuple[bool, list[str], dict[str, float]]:
    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], Mapping):
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "the moderation answer has no result")
    result = results[0]
    categories = result.get("categories")
    scores = result.get("category_scores")
    if not isinstance(categories, Mapping) or not isinstance(scores, Mapping):
        raise AiCallError(AiErrorCode.INVALID_OUTPUT, "the moderation answer has no categories")
    flagged_names = sorted(str(name) for name, on in categories.items() if on is True)
    numeric = {
        str(name): float(score)
        for name, score in scores.items()
        if isinstance(score, int | float) and not isinstance(score, bool)
    }
    return bool(result.get("flagged")), flagged_names, numeric
