"""
The twelve chat cases of `make eval` (v2 §27.16), checked by rule.

Each case asks one question in a fresh chat of a fixed insight (the cases file
holds its title, explanation and verse reference; the verse is read from the
store), through the chat service itself with the real provider, inside a
transaction that is rolled back: nothing it writes stays in the database.
Then:

- the answer shown goes through the scripture guard (patterns, the whole
  Quran); a leak must be 0;
- the kind of answer (an answer, a referral, the app's new-search message, or
  an answer the guard refused) and the level the model gave are among those
  the case accepts;
- the answer names what the case needs (the surah and number of a corrected
  verse, a difference of opinion) and none of what it must avoid, compared in
  the search form of the Arabic text;
- every reply carries the AI disclosure.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from src import clock
from src.ai.client import (
    ChatResult,
    EmbeddingResult,
    ModelClient,
    ModelImage,
    ModerationResult,
)
from src.ai.records import CallLog
from src.arabic import normalize_arabic
from src.config import AiProvider, AiStage, ProviderSettings, Settings
from src.errors import AppError, ErrorCode
from src.messages import messages_for
from src.models import Guest, Insight, InsightOrigin, Scan, ScanSource, ScanStatus
from src.pipeline.insight.guard import scripture_guard
from src.pipeline.leak_guard import LeakDetector
from src.services import chat_service

CHAT_CASES = Path(__file__).resolve().parents[2] / "tests" / "evaluation" / "chat" / "cases.json"
Kind = Literal["answer", "referral", "new_search", "refused", "failed"]
Level = Literal["a", "b", "c", "d"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerseRef(_Frozen):
    surah: int
    ayah: int


class CaseInsight(_Frozen):
    """The insight a case asks about, as the engine would have kept it."""

    id: str
    title: str
    glimpse: str
    relation: str
    quran: VerseRef
    explanation: list[dict[str, str]]
    why: dict[str, Any]
    small_step: dict[str, Any] | None = None


class CaseExpectation(_Frozen):
    kinds: list[Kind]
    # Empty: any level.
    levels: list[Level] = Field(default_factory=list)
    # Every group must be met by one of its words.
    mentions: list[list[str]] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)


class ChatCase(_Frozen):
    id: str
    source: Literal["official", "derived"]
    spec: str
    insight: str
    question: str
    expect: CaseExpectation
    why: str


class ChatCases(_Frozen):
    version: int
    description: str
    insights: list[CaseInsight]
    cases: list[ChatCase]


def load_chat_cases(path: Path = CHAT_CASES) -> ChatCases:
    cases = ChatCases.model_validate(json.loads(path.read_text(encoding="utf-8")))
    known = {insight.id for insight in cases.insights}
    unknown = sorted({case.insight for case in cases.cases} - known)
    if unknown:
        message = f"chat cases name unknown insights: {', '.join(unknown)}"
        raise ValueError(message)
    return cases


class ChatCaseRun(BaseModel):
    case: str
    source: str
    spec: str
    question: str
    expected: str
    kind: Kind
    level: str | None
    answer: str
    # What the model wrote, kept in the raw results only: a refused answer may hold scripture.
    model_answer: str | None
    disclosed: bool
    leaks: list[str]
    failures: list[str]
    passed: bool
    total_ms: int
    cost_usd: float
    calls: int


class ChatEvaluationResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    provider: str
    model: str
    runs: list[ChatCaseRun]

    @property
    def cost_usd(self) -> float:
        return sum(run.cost_usd for run in self.runs)


def describe(expect: CaseExpectation) -> str:
    """Say what a case accepts, in one short line for the report."""
    parts = [" or ".join(expect.kinds)]
    if expect.levels:
        parts.append("level " + " or ".join(expect.levels))
    return ", ".join(parts)


def _has(folded: str, word: str) -> bool:
    return normalize_arabic(word) in folded


def score(
    expect: CaseExpectation, *, kind: Kind, level: str | None, answer: str, disclosed: bool
) -> list[str]:
    """Return why an outcome does not meet the case; empty when it does."""
    failures: list[str] = []
    if kind not in expect.kinds:
        failures.append(f"kind {kind}")
    if expect.levels and level not in expect.levels:
        failures.append(f"level {level or 'none'}")
    if kind in {"refused", "failed"}:
        return failures
    if not disclosed:
        failures.append("no disclosure")
    folded = normalize_arabic(answer)
    failures += [
        f"missing {' / '.join(group)}"
        for group in expect.mentions
        if not any(_has(folded, word) for word in group)
    ]
    failures += [f"says {word}" for word in expect.avoids if _has(folded, word)]
    return failures


class _Recorder(ModelClient):
    """Pass every call through, and keep the last structured answer the model gave."""

    def __init__(self, inner: ModelClient) -> None:
        self.inner = inner
        self.last: BaseModel | None = None

    @property
    def provider(self) -> AiProvider:
        return self.inner.provider

    @property
    def settings(self) -> ProviderSettings:
        return self.inner.settings

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
        result = await self.inner.chat_json(
            schema,
            stage=stage,
            system=system,
            user=user,
            images=images,
            model=model,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )
        self.last = result.value
        return result

    async def embed(
        self, texts: Sequence[str], *, model: str | None = None, dimensions: int | None = None
    ) -> EmbeddingResult:
        return await self.inner.embed(texts, model=model, dimensions=dimensions)

    async def moderate_image(
        self, image: ModelImage, *, model: str | None = None
    ) -> ModerationResult:
        return await self.inner.moderate_image(image, model=model)


ClientFactory = Callable[[CallLog], ModelClient]


async def _insight(db: AsyncSession, spec: CaseInsight) -> Insight:
    """Store a guest, a finished scan and the case's insight, as a scan would have."""
    now = clock.utcnow()
    guest = Guest(key=secrets.token_hex(32), created_at=now, last_seen_at=now)
    db.add(guest)
    await db.flush()
    scan = Scan(
        guest_key=guest.key,
        source=ScanSource.UPLOAD,
        status=ScanStatus.DONE,
        engine="pipeline",
    )
    db.add(scan)
    await db.flush()
    insight = Insight(
        guest_key=guest.key,
        scan_id=scan.id,
        origin=InsightOrigin.SCAN,
        engine="pipeline",
        title=spec.title,
        glimpse=spec.glimpse,
        relation=spec.relation,
        quran_surah=spec.quran.surah,
        quran_ayah=spec.quran.ayah,
        quran_evidence={"relation": spec.relation},
        explanation=[{**part, "sources": []} for part in spec.explanation],
        why=spec.why,
        small_step=spec.small_step,
    )
    db.add(insight)
    await db.commit()
    return insight


async def evaluate_case(
    connection: AsyncConnection,
    settings: Settings,
    case: ChatCase,
    insight: CaseInsight,
    client_factory: ClientFactory,
    quran: LeakDetector,
    *,
    timer: Callable[[], float] = time.perf_counter,
) -> ChatCaseRun:
    """Ask one case in a fresh chat, inside a savepoint that is rolled back, and check it."""
    log = CallLog()
    recorder: list[_Recorder] = []

    def factory(call_log: CallLog) -> ModelClient:
        client = _Recorder(client_factory(call_log))
        recorder.append(client)
        return client

    kind: Kind
    level: str | None = None
    answer = ""
    disclosed = False
    started = timer()
    savepoint = await connection.begin_nested()
    maker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    leaks: list[str] = []
    try:
        async with maker() as db:
            row = await _insight(db, insight)
            try:
                reply = await chat_service.answer(
                    db,
                    settings,
                    row,
                    question=case.question,
                    key=f"eval-{case.id}",
                    client_factory=lambda _log: factory(log),
                )
            except AppError as error:
                kind = "refused" if error.code is ErrorCode.CHAT_ANSWER_REJECTED else "failed"
            else:
                kind = reply.message.kind
                level = reply.message.level
                answer = reply.message.answer
                disclosed = reply.disclosure == messages_for().ai_disclosure
                # Checked again here, apart from the service: patterns, the Quran, the store.
                if answer and await scripture_guard(quran, session=db).leaks([answer]):
                    leaks = ["answer"]
    finally:
        await savepoint.rollback()
    said = recorder[0].last if recorder else None
    model_answer = getattr(said, "answer", None)
    if level is None and said is not None:
        level = getattr(said, "level", None)
    failures = score(case.expect, kind=kind, level=level, answer=answer, disclosed=disclosed)
    failures += [f"leak in {where}" for where in leaks]
    return ChatCaseRun(
        case=case.id,
        source=case.source,
        spec=case.spec,
        question=case.question,
        expected=describe(case.expect),
        kind=kind,
        level=level,
        answer=answer,
        model_answer=model_answer,
        disclosed=disclosed,
        leaks=leaks,
        failures=failures,
        passed=not failures,
        total_ms=round((timer() - started) * 1000),
        cost_usd=round(log.total_cost_usd, 6),
        calls=len(log.records),
    )


async def run_chat_evaluation(
    connection: AsyncConnection,
    settings: Settings,
    cases: ChatCases,
    client_factory: ClientFactory,
    quran: LeakDetector,
    *,
    only: Sequence[str] = (),
    max_cost_usd: float | None = None,
    on_case: Callable[[ChatCaseRun], Awaitable[None]] | None = None,
) -> ChatEvaluationResult:
    """Ask every case, in order, until the spend cap."""
    started_at = datetime.now(UTC)
    insights = {insight.id: insight for insight in cases.insights}
    runs: list[ChatCaseRun] = []
    for case in cases.cases:
        if only and case.id not in only:
            continue
        if max_cost_usd is not None and sum(run.cost_usd for run in runs) >= max_cost_usd:
            break
        run = await evaluate_case(
            connection, settings, case, insights[case.insight], client_factory, quran
        )
        runs.append(run)
        if on_case is not None:
            await on_case(run)
    return ChatEvaluationResult(
        started_at=started_at,
        finished_at=datetime.now(UTC),
        provider=settings.ai_provider.value,
        model=settings.ai.model_for(AiStage.CHAT),
        runs=runs,
    )
