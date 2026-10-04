"""
Evaluate the insight engine on the gold scenes and the chat cases (`make eval`).

    uv run python -m src.cli.evaluate [--only scenes|chat] [--scenes a,b] [--cases a,b]
                                      [--max-cost USD] [--no-report]

Every gold scene goes through the whole scan pipeline with the active
provider (the keys of the root .env): image check, detector, scene analysis,
sensitivity guard, insight engine. Then the twelve chat cases (v2 §27.16) are
asked through the chat service, in transactions that are rolled back. It costs
money (about three cents a scene, a fraction of a cent a case); `--max-cost`
stops before a scene or a case once that much is spent, both parts together.
The raw results go to `tests/evaluation/results/evaluation-<date>.json` and
`chat-<date>.json` (not committed) and the report to docs/EVALUATION.md, the
chat cases in their own section. Exit 0 when no scripture leaked and every
reference resolved, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from src.ai.client import ModelClient, client_for
from src.ai.records import CallLog
from src.config import AiStage, RerankerKind, Settings, get_settings
from src.database import dispose_engine, get_engine, get_sessionmaker
from src.evaluation.benchmark import prepare_scenes
from src.evaluation.chat_eval import (
    CHAT_CASES,
    ChatCaseRun,
    ChatEvaluationResult,
    load_chat_cases,
    run_chat_evaluation,
)
from src.evaluation.chat_report import SECTION as CHAT_SECTION
from src.evaluation.chat_report import render_section
from src.evaluation.engine_eval import (
    ENGINE_GOLD,
    EngineFactory,
    EvaluationResult,
    SceneRun,
    load_engine_gold,
    run_evaluation,
    summary,
)
from src.evaluation.evaluation_report import render
from src.evaluation.gold import load_gold
from src.evaluation.report_sections import carry_sections, replace_section
from src.pipeline.detector import DetectorClient
from src.pipeline.engine import InsightEngine
from src.pipeline.insight.engine import ResourceCache, active_reranker, build_engine
from src.pipeline.insight.guard import quran_detector
from src.pipeline.leak_guard import LeakDetector

API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parents[1]
SCENES_DIR = API_DIR / "tests" / "evaluation" / "scenes"
RESULTS_DIR = API_DIR / "tests" / "evaluation" / "results"
REPORT_PATH = REPO_ROOT / "docs" / "EVALUATION.md"
STAGES = (AiStage.VISION, AiStage.PLANNER, AiStage.VERIFY, AiStage.COMPOSE, AiStage.EMBEDDING)


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the insight engine on the gold scenes.")
    parser.add_argument("--only", choices=("scenes", "chat"), help="run one part (default: both)")
    parser.add_argument("--scenes", default="", help="scene ids, comma separated (default: all)")
    parser.add_argument("--cases", default="", help="chat case ids, comma separated (default: all)")
    parser.add_argument("--max-cost", type=float, default=2.0)
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--gold", type=Path, default=ENGINE_GOLD, help=argparse.SUPPRESS)
    parser.add_argument("--chat-cases", type=Path, default=CHAT_CASES, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.scenes = [name for name in args.scenes.split(",") if name]
    args.cases = [name for name in args.cases.split(",") if name]
    return args


def models_of(settings: Settings) -> dict[str, str]:
    """Name the model of each measured stage, and what reranked."""
    models = {stage.value: settings.ai.model_for(stage) for stage in STAGES}
    kind = active_reranker(settings)
    models[AiStage.RERANK.value] = (
        settings.ai.rerank_model if kind is RerankerKind.LLM else kind.value
    )
    return models


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def factory_for(
    settings: Settings, http: httpx.AsyncClient, maker: async_sessionmaker[AsyncSession]
) -> EngineFactory:
    shared = ResourceCache()

    def build(log: CallLog) -> tuple[ModelClient, InsightEngine]:
        engine = build_engine(settings, http, maker, log=log, resources=shared)
        return client_for(settings, http, log=log), engine

    return build


async def _progress(run: SceneRun) -> None:
    _say(
        f"{run.scene}: {run.status}, {run.insights} insights, "
        f"{run.total_ms / 1000:.1f} s, ${run.cost_usd:.4f}"
    )


async def _case_progress(run: ChatCaseRun) -> None:
    verdict = "as expected" if run.passed else "; ".join(run.failures)
    _say(f"{run.case}: {run.kind}, level {run.level or '-'}, {verdict}, ${run.cost_usd:.4f}")


ChatClientFactory = Callable[[CallLog], ModelClient]


async def _scenes(
    args: argparse.Namespace,
    settings: Settings,
    maker: async_sessionmaker[AsyncSession],
    transport: httpx.AsyncClient,
    factory: EngineFactory | None,
) -> EvaluationResult:
    async with maker() as session:
        detector = DetectorClient(
            settings.detector_url, transport, timeout_seconds=settings.detector_timeout_seconds
        )
        scenes = await prepare_scenes(
            load_gold(SCENES_DIR / "gold.json"),
            SCENES_DIR,
            args.scenes,
            settings=settings,
            detector=detector,
        )
        return await run_evaluation(
            session,
            scenes,
            load_engine_gold(args.gold),
            factory or factory_for(settings, transport, maker),
            await quran_detector(session),
            provider=settings.ai_provider.value,
            models=models_of(settings),
            max_cost_usd=args.max_cost,
            on_scene=_progress,
        )


async def _chat(
    args: argparse.Namespace,
    settings: Settings,
    connection: AsyncConnection | None,
    maker: async_sessionmaker[AsyncSession],
    clients: ChatClientFactory,
    spent: float,
) -> ChatEvaluationResult:
    async with maker() as session:
        quran = await quran_detector(session)
    if connection is None:
        async with get_engine().connect() as own:
            try:
                return await _ask(args, settings, own, clients, quran, spent)
            finally:
                await own.rollback()
    return await _ask(args, settings, connection, clients, quran, spent)


async def _ask(
    args: argparse.Namespace,
    settings: Settings,
    connection: AsyncConnection,
    clients: ChatClientFactory,
    quran: LeakDetector,
    spent: float,
) -> ChatEvaluationResult:
    return await run_chat_evaluation(
        connection,
        settings,
        load_chat_cases(args.chat_cases),
        clients,
        quran,
        only=args.cases,
        max_cost_usd=max(args.max_cost - spent, 0.0),
        on_case=_case_progress,
    )


def _write_scenes(args: argparse.Namespace, result: EvaluationResult) -> None:
    raw = args.results_dir / f"evaluation-{result.started_at:%Y-%m-%d}.json"
    raw.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    if not args.no_report:
        previous = args.report.read_text(encoding="utf-8") if args.report.is_file() else ""
        # Hand-written sections (a comparison run, notes) and the chat cases are kept.
        report = carry_sections(previous, render(result, _relative(raw)))
        args.report.write_text(report, encoding="utf-8")
    facts = summary(result)
    _say(
        f"{facts.correct}/{facts.scenes} as expected, {facts.leaks} leaks, "
        f"{facts.unresolved}/{facts.evidence} unresolved, ${facts.cost:.4f}"
    )


def _write_chat(args: argparse.Namespace, result: ChatEvaluationResult) -> None:
    raw = args.results_dir / f"chat-{result.started_at:%Y-%m-%d}.json"
    raw.write_text(result.model_dump_json(indent=1) + "\n", encoding="utf-8")
    if not args.no_report:
        previous = args.report.read_text(encoding="utf-8") if args.report.is_file() else ""
        section = render_section(result, _relative(raw))
        args.report.write_text(replace_section(previous, CHAT_SECTION, section), encoding="utf-8")
    passed = sum(run.passed for run in result.runs)
    leaks = sum(len(run.leaks) for run in result.runs)
    _say(f"chat: {passed}/{len(result.runs)} as expected, {leaks} leaks, ${result.cost_usd:.4f}")


async def run(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    connection: AsyncConnection | None = None,
    factory: EngineFactory | None = None,
    chat_clients: ChatClientFactory | None = None,
    http: httpx.AsyncClient | None = None,
) -> int:
    """Run the evaluation; return the process exit code."""
    args = parse_args(argv)
    settings = settings or get_settings()
    maker = sessionmaker or get_sessionmaker()
    scenes: EvaluationResult | None = None
    chat: ChatEvaluationResult | None = None
    try:
        async with http or httpx.AsyncClient() as transport:
            if args.only != "chat":
                scenes = await _scenes(args, settings, maker, transport, factory)
            if args.only != "scenes":
                clients = chat_clients or (lambda log: client_for(settings, transport, log=log))
                spent = scenes.cost_usd if scenes is not None else 0.0
                chat = await _chat(args, settings, connection, maker, clients, spent)
    finally:
        if sessionmaker is None:
            await dispose_engine()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    leaked = False
    if scenes is not None:
        _write_scenes(args, scenes)
        facts = summary(scenes)
        leaked = facts.leaks > 0 or facts.unresolved > 0
    if chat is not None:
        _write_chat(args, chat)
        leaked = leaked or any(run.leaks for run in chat.runs)
    return 1 if leaked else 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
