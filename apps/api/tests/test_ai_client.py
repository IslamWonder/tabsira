"""The provider adapter, against a mock transport: no network, no model."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from src.ai.client import ModelImage, ProviderClient, client_for
from src.ai.errors import AiCallError, AiErrorCode
from src.ai.records import CallKind, CallLog
from src.config import AiProvider, AiStage, OpenAISettings, OvhSettings, ProviderSettings

KEY = "sk-test-key-123"


class Colours(BaseModel):
    left: str
    right: str


Handler = Callable[[httpx.Request], httpx.Response]


class Clock:
    """A clock that moves 0.25 s each time it is read."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.25
        return self.now


class Harness:
    """A client wired to a list of canned responses, recording requests and sleeps."""

    def __init__(
        self,
        responses: list[httpx.Response | Exception],
        *,
        provider: AiProvider = AiProvider.OVH,
        settings: ProviderSettings | None = None,
        max_retries: int = 2,
    ) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.log = CallLog()
        block = settings or (
            OvhSettings(api_key=KEY, vision_model="Qwen3.8-27B")
            if provider == AiProvider.OVH
            else OpenAISettings(
                api_key=KEY,
                vision_model="gpt-5.4-mini-2026-03-17",
                guard_model="omni-moderation-latest",
                embedding_model="text-embedding-3-small",
            )
        )
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        self.client = ProviderClient(
            provider,
            block,
            self.http,
            timeout_seconds=5,
            max_retries=max_retries,
            backoff_seconds=0.5,
            log=self.log,
            sleep=self.sleep,
            clock=Clock(),
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def chat(content: Any, *, finish: str = "stop", usage: dict[str, Any] | None = None, **message):
    payload = {
        "choices": [
            {
                "message": {"role": "assistant", "content": content, **message},
                "finish_reason": finish,
            }
        ],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50},
    }
    return httpx.Response(200, json=payload)


GOOD = json.dumps({"left": "red", "right": "blue"})


async def ask(harness: Harness, **kwargs: Any):
    return await harness.client.chat_json(
        Colours, stage=AiStage.VISION, system="sys", user="which colours?", **kwargs
    )


# ─── Chat with structured output ───────────────────────────────────


async def test_a_structured_answer_is_validated_and_recorded():
    harness = Harness(
        [
            chat(
                GOOD,
                usage={
                    "prompt_tokens": 1000,
                    "completion_tokens": 400,
                    "completion_tokens_details": {"reasoning_tokens": 300},
                },
                reasoning="the hidden thoughts",
            )
        ]
    )

    result = await ask(harness, images=[ModelImage(b"\xff\xd8jpeg")])

    assert result.value == Colours(left="red", right="blue")
    record = result.record
    assert record.provider is AiProvider.OVH
    assert record.model == "Qwen3.8-27B"
    assert record.stage is AiStage.VISION
    assert record.kind is CallKind.CHAT
    assert record.ok
    assert record.error_code is None
    assert record.attempts == 1
    assert record.retried_errors == ()
    assert record.finish_reason == "stop"
    assert record.latency_ms == 250
    assert record.usage.reasoning_tokens == 300
    assert record.cost_usd == pytest.approx((1000 * 0.47 + 400 * 3.19) / 1e6)
    assert harness.log.records == [record]


async def test_the_request_carries_the_strict_schema_the_image_and_the_key():
    harness = Harness([chat(GOOD)])

    await ask(harness, images=[ModelImage(b"abc", "image/png")], max_output_tokens=900)

    request = harness.requests[0]
    assert str(request.url) == "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = harness.body()
    assert body["model"] == "Qwen3.8-27B"
    assert body["max_completion_tokens"] == 900
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["required"] == ["left", "right"]
    system, user = body["messages"]
    assert system == {"role": "system", "content": "sys"}
    assert user["content"] == [
        {"type": "text", "text": "which colours?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}},
    ]
    # The measured default (docs/BENCHMARK.md); nothing else the settings did not ask for.
    assert body["reasoning_effort"] == "none"
    assert "temperature" not in body


async def test_reasoning_effort_comes_from_the_settings_and_can_be_overridden():
    settings = OvhSettings(api_key=KEY, vision_model="Qwen3.8-27B", reasoning_effort="low")
    harness = Harness([chat(GOOD), chat(GOOD), chat(GOOD)], settings=settings)

    await ask(harness)
    await ask(harness, reasoning_effort="high", temperature=0.2, model="Qwen3.5-9B")
    await ask(harness, reasoning_effort="")

    assert harness.body(0)["reasoning_effort"] == "low"
    assert harness.body(1)["reasoning_effort"] == "high"
    assert harness.body(1)["temperature"] == 0.2
    assert harness.body(1)["model"] == "Qwen3.5-9B"
    assert "reasoning_effort" not in harness.body(2)


@pytest.mark.parametrize(
    "content",
    [
        f"<think>let me see</think>\n{GOOD}",
        f"```json\n{GOOD}\n```",
        f"```\n{GOOD}\n```",
    ],
)
async def test_wrappers_some_models_add_around_json_are_removed(content):
    harness = Harness([chat(content)])

    assert (await ask(harness)).value.left == "red"


async def test_a_server_error_is_retried_with_backoff_and_usage_adds_up():
    harness = Harness(
        [
            httpx.Response(503, json={"error": {"message": "overloaded"}}),
            chat("not json at all"),
            chat(GOOD),
        ]
    )

    result = await ask(harness)

    assert result.record.attempts == 3
    assert result.record.retried_errors == (AiErrorCode.SERVER_ERROR, AiErrorCode.INVALID_OUTPUT)
    assert harness.sleeps == [0.5, 1.0]
    # The failed answer was billed too.
    assert result.record.usage.input_tokens == 200


async def test_retries_are_bounded_and_the_failure_is_recorded():
    harness = Harness([chat("{}"), chat("{}"), chat("{}")])

    with pytest.raises(AiCallError) as caught:
        await ask(harness)

    error = caught.value
    assert error.code is AiErrorCode.INVALID_OUTPUT
    assert "does not match Colours (2 errors)" in str(error)
    assert error.record is not None
    assert not error.record.ok
    assert error.record.error_code is AiErrorCode.INVALID_OUTPUT
    assert error.record.attempts == 3
    assert error.record.retried_errors == (AiErrorCode.INVALID_OUTPUT,) * 2
    assert harness.log.records == [error.record]
    assert harness.responses == []


async def test_no_retry_when_retries_are_off():
    harness = Harness([httpx.Response(500, text="boom")], max_retries=0)

    with pytest.raises(AiCallError) as caught:
        await ask(harness)

    assert caught.value.code is AiErrorCode.SERVER_ERROR
    assert "HTTP 500: boom" in str(caught.value)
    assert harness.sleeps == []


async def test_a_rate_limit_waits_as_long_as_the_provider_asks_within_a_cap():
    harness = Harness(
        [
            httpx.Response(429, headers={"retry-after": "3"}, json={"error": "slow down"}),
            httpx.Response(429, headers={"retry-after": "120"}),
            httpx.Response(429, headers={"retry-after": "soon"}),
            chat(GOOD),
        ],
        max_retries=3,
    )

    await ask(harness)

    assert harness.sleeps == [3.0, 30.0, 2.0]


async def test_timeouts_and_network_errors_are_retried():
    harness = Harness(
        [httpx.ReadTimeout("slow"), httpx.ConnectError("refused"), chat(GOOD)],
    )

    result = await ask(harness)

    assert result.record.attempts == 3


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.ReadTimeout("slow"), AiErrorCode.TIMEOUT),
        (httpx.ConnectError("refused"), AiErrorCode.NETWORK),
        (httpx.ConnectTimeout("no route"), AiErrorCode.NETWORK),
        (httpx.PoolTimeout("busy"), AiErrorCode.TIMEOUT),
        (httpx.Response(401, json={"error": {"message": "bad key"}}), AiErrorCode.UNAUTHORIZED),
        (httpx.Response(403, json=["forbidden"]), AiErrorCode.UNAUTHORIZED),
        (httpx.Response(404, json={"error": {"message": "no model"}}), AiErrorCode.NOT_FOUND),
        (httpx.Response(400, json={"error": {"message": "bad"}}), AiErrorCode.BAD_REQUEST),
        (httpx.Response(422, json={"detail": "x"}), AiErrorCode.BAD_REQUEST),
        (httpx.Response(418, text="teapot"), AiErrorCode.BAD_REQUEST),
        (httpx.Response(408, text=""), AiErrorCode.TIMEOUT),
        (httpx.Response(502, text="bad gateway"), AiErrorCode.SERVER_ERROR),
        (httpx.Response(200, text="<html>"), AiErrorCode.SERVER_ERROR),
        (httpx.Response(200, json=[1, 2]), AiErrorCode.SERVER_ERROR),
        (httpx.Response(200, json={"choices": []}), AiErrorCode.INVALID_OUTPUT),
        (httpx.Response(200, json={"choices": ["x"]}), AiErrorCode.INVALID_OUTPUT),
        (httpx.Response(200, json={"choices": [{"message": "x"}]}), AiErrorCode.INVALID_OUTPUT),
        (chat(None, refusal="I cannot help"), AiErrorCode.REFUSED),
        (chat('{"left": "re', finish="length"), AiErrorCode.TRUNCATED),
        (chat("   "), AiErrorCode.INVALID_OUTPUT),
        (chat(None), AiErrorCode.INVALID_OUTPUT),
    ],
)
async def test_each_failure_has_its_code(response, code):
    harness = Harness([response], max_retries=0)

    with pytest.raises(AiCallError) as caught:
        await ask(harness)

    assert caught.value.code is code
    assert caught.value.record is not None
    assert KEY not in str(caught.value)


async def test_the_provider_message_is_kept_short_in_the_error():
    harness = Harness([httpx.Response(400, json={"error": {"message": "x" * 500}})], max_retries=0)

    with pytest.raises(AiCallError) as caught:
        await ask(harness)

    assert str(caught.value) == "bad_request: HTTP 400: " + "x" * 200


async def test_a_finish_reason_that_is_not_text_is_ignored():
    harness = Harness(
        [httpx.Response(200, json={"choices": [{"finish_reason": 3}], "x": 1})], max_retries=0
    )

    with pytest.raises(AiCallError):
        await ask(harness)

    assert harness.log.records[0].finish_reason is None


async def test_a_call_without_a_model_a_key_or_with_gpt_oss_is_refused_before_sending():
    no_model = Harness([], settings=OvhSettings(api_key=KEY, vision_model=""))
    no_key = Harness([], settings=OvhSettings(vision_model="Qwen3.8-27B"))
    forbidden = Harness([])

    with pytest.raises(AiCallError) as missing:
        await ask(no_model)
    with pytest.raises(AiCallError) as keyless:
        await ask(no_key)
    with pytest.raises(AiCallError) as oss:
        await ask(forbidden, model="gpt-oss-120b")

    assert missing.value.code is AiErrorCode.NOT_CONFIGURED
    assert "no vision model is set for ovh" in str(missing.value)
    assert keyless.value.code is AiErrorCode.NOT_CONFIGURED
    assert oss.value.code is AiErrorCode.FORBIDDEN_MODEL
    for harness in (no_model, no_key, forbidden):
        assert harness.requests == []
        assert harness.log.records == []


async def test_a_model_without_a_price_is_recorded_without_cost():
    harness = Harness([chat(GOOD)])

    result = await ask(harness, model="Mistral-Small-3.2-24B-Instruct-2506")

    assert result.record.cost_usd is None


# ─── Embeddings ────────────────────────────────────────────────────


def embeddings(*vectors: tuple[int, list[float]]) -> httpx.Response:
    data = [{"index": index, "embedding": vector} for index, vector in vectors]
    return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 7}})


async def test_embeddings_come_back_in_input_order():
    harness = Harness([embeddings((1, [0.5, 0.5]), (0, [1, 0]))], provider=AiProvider.OPENAI)

    result = await harness.client.embed(["مطر", "زيتون"], dimensions=2)

    assert result.vectors == [[1.0, 0.0], [0.5, 0.5]]
    assert harness.body() == {
        "model": "text-embedding-3-small",
        "input": ["مطر", "زيتون"],
        "dimensions": 2,
    }
    assert str(harness.requests[0].url).endswith("/v1/embeddings")
    assert result.record.kind is CallKind.EMBEDDING
    assert result.record.stage is AiStage.EMBEDDING
    assert result.record.cost_usd == pytest.approx(7 * 0.02 / 1e6)


async def test_embeddings_use_the_given_model_and_send_no_dimensions_by_default():
    harness = Harness([embeddings((0, [1.0]))])

    await harness.client.embed(["x"], model="bge-m3")

    assert harness.body() == {"model": "bge-m3", "input": ["x"]}


@pytest.mark.parametrize(
    "response",
    [
        embeddings((0, [1.0])),
        httpx.Response(200, json={"data": [{"index": 0}, {"index": 1, "embedding": [1]}]}),
        httpx.Response(200, json={"data": [{"index": "a", "embedding": [1]}, {"index": 1}]}),
        httpx.Response(200, json={"data": "nope"}),
    ],
)
async def test_a_malformed_embedding_answer_is_refused(response):
    harness = Harness([response], max_retries=0)

    with pytest.raises(AiCallError) as caught:
        await harness.client.embed(["a", "b"], model="bge-m3")

    assert caught.value.code is AiErrorCode.INVALID_OUTPUT


# ─── Moderation ────────────────────────────────────────────────────


def moderation(**result: Any) -> httpx.Response:
    return httpx.Response(200, json={"id": "modr-1", "results": [result]})


async def test_image_moderation_returns_the_flagged_categories():
    harness = Harness(
        [
            moderation(
                flagged=True,
                categories={"sexual": False, "violence": True, "violence/graphic": True},
                category_scores={"sexual": 0.01, "violence": 0.9, "odd": "x", "flag": True},
            )
        ],
        provider=AiProvider.OPENAI,
    )

    result = await harness.client.moderate_image(ModelImage(b"img"))

    assert result.flagged
    assert result.categories == ["violence", "violence/graphic"]
    assert result.scores == {"sexual": 0.01, "violence": 0.9}
    assert harness.body() == {
        "model": "omni-moderation-latest",
        "input": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aW1n"}}],
    }
    assert result.record.kind is CallKind.MODERATION
    assert result.record.stage is AiStage.GUARD
    assert result.record.cost_usd == 0.0


async def test_ovh_has_no_image_moderation():
    harness = Harness([])

    with pytest.raises(AiCallError) as caught:
        await harness.client.moderate_image(ModelImage(b"img"))

    assert caught.value.code is AiErrorCode.NOT_SUPPORTED
    assert harness.requests == []


async def test_text_moderation_sends_the_text_and_returns_the_scores():
    harness = Harness(
        [
            moderation(
                flagged=True,
                categories={"harassment": True, "hate": False},
                category_scores={"harassment": 0.91, "hate": 0.02},
            )
        ],
        provider=AiProvider.OPENAI,
    )

    result = await harness.client.moderate_text("نص للفحص")

    assert result.flagged
    assert result.categories == ["harassment"]
    assert result.scores == {"harassment": 0.91, "hate": 0.02}
    assert harness.body() == {"model": "omni-moderation-latest", "input": "نص للفحص"}
    assert result.record.kind is CallKind.MODERATION
    assert result.record.stage is AiStage.GUARD


async def test_ovh_has_no_text_moderation_and_makes_no_request():
    harness = Harness([])

    with pytest.raises(AiCallError) as caught:
        await harness.client.moderate_text("نص")

    assert caught.value.code is AiErrorCode.NOT_SUPPORTED
    assert harness.requests == []


async def test_a_client_that_does_not_override_text_moderation_refuses_it():
    from tests.fakes import FakeModelClient

    with pytest.raises(AiCallError) as caught:
        await FakeModelClient(AiProvider.OPENAI).moderate_text("نص")

    assert caught.value.code is AiErrorCode.NOT_SUPPORTED


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"results": []}),
        httpx.Response(200, json={"results": ["x"]}),
        moderation(flagged=False, categories=None, category_scores={}),
    ],
)
async def test_a_malformed_moderation_answer_is_refused(response):
    harness = Harness([response], provider=AiProvider.OPENAI, max_retries=0)

    with pytest.raises(AiCallError) as caught:
        await harness.client.moderate_image(ModelImage(b"img"))

    assert caught.value.code is AiErrorCode.INVALID_OUTPUT


# ─── Factory ───────────────────────────────────────────────────────


async def test_the_factory_builds_the_active_or_the_named_provider(make_settings):
    settings = make_settings(
        ai_provider="openai",
        ai_timeout_seconds=12,
        ai_max_retries=1,
        ai_retry_backoff_seconds=0,
        ai_openai={"api_key": KEY, "vision_model": "gpt-5.4-mini-2026-03-17"},
    )
    log = CallLog()
    responses = [httpx.Response(500), chat(GOOD)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: responses.pop(0))) as http:
        active = client_for(settings, http, log=log)
        named = client_for(settings, http, provider=AiProvider.OVH)

        assert active.provider is AiProvider.OPENAI
        assert active.settings is settings.ai_openai
        assert named.provider is AiProvider.OVH
        assert named.settings is settings.ai_ovh

        # One retry is allowed, after the configured backoff.
        result = await active.chat_json(Colours, stage=AiStage.VISION, system="s", user="u")

    assert result.record.attempts == 2
    assert log.records == [result.record]


async def test_a_client_without_a_log_still_returns_its_record():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: chat(GOOD))) as http:
        client = ProviderClient(
            AiProvider.OVH,
            OvhSettings(api_key=KEY, vision_model="Qwen3.8-27B"),
            http,
            timeout_seconds=1,
            max_retries=0,
            backoff_seconds=0,
        )
        result = await client.chat_json(Colours, stage=AiStage.VISION, system="s", user="u")

    assert result.record.ok


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('  ```json   {"a": 1}   ```  ', '{"a": 1}'),
        ("```json```", ""),
        ("``````", ""),
        ("```json\n{}\n``", "```json\n{}\n``"),
        ('<think>x</think>```json\n{"a": 1}\n```', '{"a": 1}'),
        ("```a``` b ```", "a``` b"),
    ],
)
def test_a_code_fence_around_json_is_removed(content, expected):
    from src.ai.client import _json_text

    assert _json_text(content) == expected


def test_a_long_run_of_spaces_in_a_fence_is_read_in_linear_time():
    import time

    from src.ai.client import _json_text

    content = "```json" + " " * 200_000 + "x" + " " * 200_000 + "``"
    started = time.monotonic()
    assert _json_text(content) == content.strip()
    assert time.monotonic() - started < 1
    fenced = "```" + " " * 200_000 + "```"
    assert _json_text(fenced) == ""
